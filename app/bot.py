import logging
import sqlite3
import os
import uuid
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from py3xui import Api, Client

# Настройки из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
XUI_PANEL_URL = os.getenv('XUI_PANEL_URL')
XUI_USERNAME = os.getenv('XUI_USERNAME')
XUI_PASSWORD = os.getenv('XUI_PASSWORD')
INBOUND_ID = int(os.getenv('INBOUND_ID', '1'))
DATA_LIMIT_GB = int(os.getenv('DATA_LIMIT_GB', '10'))
BOT_USERNAME = os.getenv('BOT_USERNAME')

# Проверка обязательных переменных
if not all([BOT_TOKEN, XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD]):
    missing = []
    if not BOT_TOKEN: missing.append('BOT_TOKEN')
    if not XUI_PANEL_URL: missing.append('XUI_PANEL_URL')
    if not XUI_USERNAME: missing.append('XUI_USERNAME')
    if not XUI_PASSWORD: missing.append('XUI_PASSWORD')
    raise Exception(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")

# Настройки путей
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_NAME = DATA_DIR / "users.db"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ========== ФУНКЦИИ БАЗЫ ДАННЫХ ==========

def init_db():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                language_code TEXT,
                subscription_url TEXT,
                xui_client_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"База данных инициализирована: {DB_NAME}")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")


def add_user(telegram_id, username, full_name, language_code, subscription_url, xui_client_id):
    """Добавление пользователя в базу"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO users (telegram_id, username, full_name, language_code, subscription_url, xui_client_id) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, username, full_name, language_code, subscription_url, xui_client_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Пользователь {telegram_id} уже существует")
        return False
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
        return False


def get_user(telegram_id):
    """Получение пользователя по Telegram ID"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        logger.error(f"Ошибка получения пользователя: {e}")
        return None


# ========== ФУНКЦИИ 3X-UI ==========

def login_to_xui():
    """Авторизация в 3x-ui"""
    try:
        api = Api(
            XUI_PANEL_URL,
            XUI_USERNAME,
            XUI_PASSWORD,
            use_tls_verify=False
        )
        api.login()
        logger.info("✅ Успешная авторизация в 3x-ui")
        return api
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации в 3x-ui: {e}")
        return None


def generate_client_email(telegram_id, username):
    """Генерация email на основе данных Telegram"""
    if username:
        email = f"{username}@telegram.{telegram_id}.vpn"
    else:
        email = f"user{telegram_id}@telegram.vpn"
    return email.lower()


def create_xui_client(telegram_id, username, full_name, data_limit_gb=10):
    """Создание клиента в 3x-ui"""
    try:
        api = login_to_xui()
        if not api:
            return None

        # Генерируем уникальный ID для клиента
        client_id = str(uuid.uuid4())

        # Генерируем email на основе Telegram данных
        email = generate_client_email(telegram_id, username)

        # Создаем конфигурацию клиента
        client_config = Client(
            id=client_id,
            email=email,
            flow="xtls-rprx-vision",
            enable=True,
            limitIp=0,
            totalGB=data_limit_gb * 1073741824,  # Конвертация в байты
            expiryTime=0,
            tgId=str(telegram_id),
            subId=""
        )

        # Добавляем клиента в инбаунд
        result = api.client.add(INBOUND_ID, [client_config])

        if result:
            # Генерируем ссылку для подписки
            subscription_url = generate_subscription_url(client_id)
            logger.info(f"✅ Клиент создан: {email} (ID: {client_id})")
            return {
                'client_id': client_id,
                'subscription_url': subscription_url,
                'email': email,
                'success': True
            }
        else:
            logger.error("❌ Не удалось создать клиента в 3x-ui")
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка создания клиента: {e}")
        return None


def generate_subscription_url(client_id):
    """Генерация ссылки для подписки"""
    try:
        base_url = XUI_PANEL_URL.rstrip('/')
        subscription_url = f"{base_url}/sub/{INBOUND_ID}/{client_id}"
        logger.info(f"🔗 Сгенерирована ссылка: {subscription_url}")
        return subscription_url
    except Exception as e:
        logger.error(f"❌ Ошибка генерации ссылки: {e}")
        return f"{XUI_PANEL_URL}/sub/{client_id}"


def test_xui_connection():
    """Тестирование подключения к 3x-ui"""
    try:
        api = login_to_xui()
        if api:
            # Пробуем получить список инбаундов
            inbounds = api.inbound.get()
            if inbounds:
                logger.info("✅ Подключение к 3x-ui успешно")
                return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования подключения: {e}")
        return False


def get_existing_client(telegram_id):
    """Поиск существующего клиента по Telegram ID"""
    try:
        api = login_to_xui()
        if not api:
            return None

        # Получаем информацию об инбаунде
        inbound = api.inbound.get(INBOUND_ID)
        if not inbound:
            return None

        # Ищем клиента с matching tgId
        settings = inbound.get('settings', {})
        clients = settings.get('clients', [])

        for client in clients:
            if client.get('tgId') == str(telegram_id):
                client_id = client.get('id')
                subscription_url = generate_subscription_url(client_id)
                email = client.get('email', 'Не указан')
                return {
                    'client_id': client_id,
                    'subscription_url': subscription_url,
                    'email': email,
                    'existing': True
                }

        return None

    except Exception as e:
        logger.error(f"❌ Ошибка поиска клиента: {e}")
        return None


# ========== TELEGRAM БОТ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user

    # Приветственное сообщение с кнопкой регистрации
    keyboard = [
        [InlineKeyboardButton("🚀 Начать использовать VPN", callback_data="register")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я бот для быстрого создания VPN подключений\n"
        f"🔐 **Регистрация за 1 клик** - используйте ваш Telegram аккаунт\n\n"
        f"✨ **Преимущества:**\n"
        f"• ⚡ Мгновенная регистрация\n"
        f"• 🔒 Без ввода email и паролей\n"
        f"• 🆓 Бесплатный трафик: {DATA_LIMIT_GB} GB\n"
        f"• 🌐 Доступ к заблокированным ресурсам\n\n"
        f"Нажмите **«🚀 Начать использовать VPN»** чтобы получить персональную ссылку!"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()

    if query.data == "register":
        await register_user(query, context)
    elif query.data == "status":
        await show_status(query, context)
    elif query.data == "help":
        await help_command(query, context)


async def register_user(query, context):
    """Регистрация пользователя через Telegram OAuth"""
    user = query.from_user

    # Проверяем, не зарегистрирован ли уже пользователь
    existing_user = get_user(user.id)

    if existing_user:
        subscription_url = existing_user[5]  # subscription_url в 6-й колонке
        await query.edit_message_text(
            f"✅ **Вы уже зарегистрированы!**\n\n"
            f"🔗 **Ваша ссылка для подключения:**\n"
            f"`{subscription_url}`\n\n"
            f"Используйте кнопку '📊 Мой статус' для подробной информации.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Сразу начинаем процесс регистрации
    await query.edit_message_text(
        "⏳ **Создаем ваш VPN аккаунт...**\n\n"
        "Используем данные вашего Telegram аккаунта...",
        parse_mode=ParseMode.MARKDOWN
    )

    # Сначала проверяем, нет ли существующего клиента
    existing_client = get_existing_client(user.id)

    if existing_client:
        # Используем существующего клиента
        client_result = existing_client
    else:
        # Создаем нового клиента
        client_result = create_xui_client(
            user.id,
            user.username,
            user.full_name,
            DATA_LIMIT_GB
        )

    if client_result and client_result.get('client_id'):
        # Сохраняем пользователя в базу
        success = add_user(
            user.id,
            user.username,
            user.full_name,
            user.language_code,
            client_result['subscription_url'],
            client_result['client_id']
        )

        if success:
            if client_result.get('existing', False):
                message_header = "🔄 **Найден существующий аккаунт!**"
            else:
                message_header = "🎉 **Регистрация успешна!**"

            user_info = (
                f"👤 **Telegram пользователь:** {user.full_name}\n"
                f"🆔 **ID:** {user.id}\n"
            )
            if user.username:
                user_info += f"📱 **Username:** @{user.username}\n"

            await query.edit_message_text(
                f"{message_header}\n\n"
                f"{user_info}\n"
                f"📧 **Сгенерированный email:** {client_result['email']}\n"
                f"📊 **Лимит трафика:** {DATA_LIMIT_GB} GB\n\n"
                f"🔗 **Ваша ссылка для подключения:**\n"
                f"`{client_result['subscription_url']}`\n\n"
                f"📱 **Как использовать:**\n"
                f"1. Скопируйте ссылку выше\n"
                f"2. Вставьте в ваш VPN клиент\n"
                f"3. Активируйте подключение\n\n"
                f"🛡️ **Приятного использования безопасного интернета!**",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                "❌ **Ошибка сохранения данных!**\n\n"
                "VPN аккаунт создан, но возникла ошибка при сохранении в базе. "
                "Обратитесь к администратору.",
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await query.edit_message_text(
            "❌ **Ошибка создания VPN аккаунта!**\n\n"
            "Возможные причины:\n"
            "• Панель 3x-ui недоступна\n"
            "• Неправильные логин/пароль администратора\n"
            "• Инбаунд не найден\n"
            "• Технические работы\n\n"
            "Попробуйте позже или обратитесь к администратору.",
            parse_mode=ParseMode.MARKDOWN
        )


async def show_status(query, context):
    """Показать статус пользователя"""
    user = query.from_user
    user_data = get_user(user.id)

    if user_data:
        _, telegram_id, username, full_name, language_code, subscription_url, xui_client_id, created_at = user_data

        status_text = (
            f"✅ **Ваш VPN аккаунт активен**\n\n"
            f"👤 **Telegram пользователь:** {full_name or 'Не указано'}\n"
        )

        if username:
            status_text += f"📱 **Username:** @{username}\n"

        status_text += (
            f"🆔 **Telegram ID:** {telegram_id}\n"
            f"📊 **Лимит трафика:** {DATA_LIMIT_GB} GB\n"
            f"📅 **Регистрация:** {created_at[:10]}\n"
            f"🆔 **ID клиента:** {xui_client_id}\n\n"
        )

        if subscription_url:
            status_text += f"🔗 **Ссылка для подключения:**\n`{subscription_url}`\n\n"

        status_text += (
            "💡 **Советы:**\n"
            "• Обновите подписку в клиенте если подключение не работает\n"
            "• Сохраните ссылку в надежном месте\n"
            "• Для перерегистрации удалите старую подписку из клиента"
        )

        await query.edit_message_text(status_text, parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = [
            [InlineKeyboardButton("🚀 Зарегистрироваться", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "❌ **Вы не зарегистрированы!**\n\n"
            "Нажмите кнопку ниже чтобы создать VPN аккаунт "
            "используя ваш Telegram профиль.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )


async def help_command(query, context):
    """Команда помощи"""
    support_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "администратору"

    help_text = (
        "ℹ️ **Помощь по использованию VPN бота**\n\n"
        "🔸 **Как зарегистрироваться:**\n"
        "1. Нажмите '🚀 Начать использовать VPN'\n"
        "2. Бот автоматически создаст аккаунт\n"
        "3. Получите персональную ссылку\n\n"
        "🔸 **Как подключиться:**\n"
        "1. Скопируйте полученную ссылку\n"
        "2. Вставьте в ваш VPN клиент\n"
        "3. Активируйте подключение\n\n"
        "🔸 **Поддерживаемые клиенты:**\n"
        "• V2RayN (Windows)\n"
        "• Shadowrocket (iOS)\n"
        "• V2RayNG (Android)\n"
        "• Qv2ray (Linux/Mac/Windows)\n\n"
        "🔸 **Лимиты:**\n"
        f"• Трафик: {DATA_LIMIT_GB} GB\n"
        "• Без ограничения по времени\n"
        "• Автопродление не требуется\n\n"
        f"🆘 **Поддержка:** {support_mention}\n\n"
        "🔐 **Безопасность:**\n"
        "• Регистрация через Telegram OAuth\n"
        "• Не требуем email и пароли\n"
        "• Ваши данные защищены"
    )
    await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    user = update.effective_user
    user_data = get_user(user.id)

    if user_data:
        subscription_url = user_data[5]
        await update.message.reply_text(
            f"🔗 **Ваша ссылка для подключения:**\n`{subscription_url}`\n\n"
            f"Используйте /start для полной информации о аккаунте.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🚀 Зарегистрироваться", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Вы не зарегистрированы! Нажмите кнопку ниже для регистрации.",
            reply_markup=reply_markup
        )


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестирования подключения к 3x-ui"""
    await update.message.reply_text("🧪 Тестируем подключение к 3x-ui...")

    if test_xui_connection():
        await update.message.reply_text("✅ Подключение к 3x-ui успешно!")
    else:
        await update.message.reply_text("❌ Не удалось подключиться к 3x-ui")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)


def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск VPN Telegram бота с OAuth...")
    logger.info(f"🔗 3x-ui панель: {XUI_PANEL_URL}")
    logger.info(f"📊 Лимит данных: {DATA_LIMIT_GB} GB")
    logger.info(f"🎯 Inbound ID: {INBOUND_ID}")
    logger.info(f"💾 База данных: {DB_NAME}")

    # Инициализация базы данных
    init_db()

    # Тестируем подключение при запуске
    logger.info("🧪 Тестируем подключение к 3x-ui...")
    if not test_xui_connection():
        logger.warning("⚠️ Не удалось подключиться к 3x-ui при запуске")

    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе с Telegram OAuth!")
    application.run_polling()


if __name__ == '__main__':
    main()
