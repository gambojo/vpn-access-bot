import logging
import sqlite3
import requests
import os
import re
import json
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройки из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
XUI_PANEL_URL = os.getenv('XUI_PANEL_URL')
XUI_USERNAME = os.getenv('XUI_USERNAME')
XUI_PASSWORD = os.getenv('XUI_PASSWORD')
INBOUND_ID = os.getenv('INBOUND_ID', '1')  # ID существующего инбаунда
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


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    full_name TEXT,
                    email TEXT,
                    xui_client_id TEXT,
                    subscription_url TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"База данных инициализирована: {self.db_path}")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")

    def add_user(self, telegram_id, username, full_name, email, xui_client_id, subscription_url):
        """Добавление пользователя в базу"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (telegram_id, username, full_name, email, xui_client_id, subscription_url) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (telegram_id, username, full_name, email, xui_client_id, subscription_url)
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

    def get_user(self, telegram_id):
        """Получение пользователя по Telegram ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            conn.close()
            return user
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None


class XUIManager:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def login(self):
        """Авторизация в 3x-ui панели"""
        try:
            login_data = {
                "username": self.username,
                "password": self.password
            }

            logger.info(f"Попытка авторизации в {self.panel_url}")

            response = self.session.post(
                f"{self.panel_url}/login",
                data=login_data,
                timeout=30
            )

            if response.status_code == 200:
                logger.info("✅ Успешная авторизация в 3x-ui")
                return True
            else:
                logger.error(f"❌ Ошибка авторизации: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка при авторизации: {e}")
            return False

    def get_inbounds(self):
        """Получение списка всех инбаундов"""
        try:
            response = self.session.get(
                f"{self.panel_url}/panel/api/inbounds/list",
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                inbounds = data.get('data', [])
                logger.info(f"📡 Найдено инбаундов: {len(inbounds)}")
                for inbound in inbounds:
                    logger.info(
                        f"  - ID: {inbound.get('id')}, Имя: {inbound.get('remark')}, Порт: {inbound.get('port')}")
                return inbounds
            else:
                logger.error(f"❌ Ошибка получения инбаундов: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"❌ Ошибка при получении инбаундов: {e}")
            return []

    def get_inbound_by_id(self, inbound_id):
        """Получение конкретного инбаунда по ID"""
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            if str(inbound.get('id')) == str(inbound_id):
                logger.info(f"✅ Найден инбаунд: {inbound.get('remark')} (ID: {inbound.get('id')})")
                return inbound
        logger.error(f"❌ Инбаунд с ID {inbound_id} не найден")
        return None

    def create_client(self, email, telegram_id, inbound_id, data_limit_gb=10):
        """Создание клиента в существующем инбаунде"""
        if not self.login():
            return None

        # Получаем целевой инбаунд
        target_inbound = self.get_inbound_by_id(inbound_id)
        if not target_inbound:
            logger.error(f"❌ Не удалось найти инбаунд с ID {inbound_id}")
            return None

        try:
            # Парсим настройки инбаунда
            settings = target_inbound.get('settings', '{}')
            if isinstance(settings, str):
                settings = json.loads(settings)

            clients = settings.get('clients', [])
            logger.info(f"👥 Текущее количество клиентов в инбаунде: {len(clients)}")

            # Проверяем, нет ли уже клиента с таким Telegram ID
            for client in clients:
                if client.get('tgId') == str(telegram_id):
                    logger.info(f"✅ Клиент для Telegram ID {telegram_id} уже существует")
                    subscription_url = self.generate_subscription_url(target_inbound, client['id'])
                    return {
                        'client_id': client['id'],
                        'subscription_url': subscription_url,
                        'existing': True
                    }

            # Создаем нового клиента
            new_client = {
                "id": self.generate_client_id(),
                "email": email,
                "enable": True,
                "flow": "xtls-rprx-vision",
                "limitIp": 0,
                "totalGB": data_limit_gb * 1073741824,  # Конвертация в байты (1GB = 1073741824 bytes)
                "expiryTime": 0,
                "tgId": str(telegram_id),
                "subId": ""
            }

            clients.append(new_client)
            settings['clients'] = clients

            # Подготавливаем данные для обновления инбаунда
            update_data = {
                "up": target_inbound.get('up', 0),
                "down": target_inbound.get('down', 0),
                "total": target_inbound.get('total', 0),
                "remark": target_inbound.get('remark', ''),
                "enable": target_inbound.get('enable', True),
                "expiryTime": target_inbound.get('expiryTime', 0),
                "listen": target_inbound.get('listen', ''),
                "port": target_inbound.get('port', 0),
                "protocol": target_inbound.get('protocol', ''),
                "settings": json.dumps(settings),
                "streamSettings": json.dumps(target_inbound.get('streamSettings', {})),
                "sniffing": json.dumps(target_inbound.get('sniffing', {})),
                "tag": target_inbound.get('tag', '')
            }

            # Обновляем инбаунд с новым клиентом
            logger.info(f"🔄 Добавляем нового клиента в инбаунд {target_inbound.get('remark')}")
            update_response = self.session.post(
                f"{self.panel_url}/panel/api/inbounds/update/{target_inbound['id']}",
                data=update_data,
                timeout=30
            )

            if update_response.status_code == 200:
                result = update_response.json()
                if result.get('success'):
                    logger.info(f"✅ Клиент создан: {email} (ID: {new_client['id']})")

                    # Генерируем ссылку для подписки
                    subscription_url = self.generate_subscription_url(target_inbound, new_client['id'])
                    return {
                        'client_id': new_client['id'],
                        'subscription_url': subscription_url,
                        'existing': False
                    }
                else:
                    logger.error(f"❌ Ошибка от 3x-ui: {result.get('msg')}")
            else:
                logger.error(f"❌ HTTP ошибка: {update_response.status_code} - {update_response.text}")

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка при создании клиента: {e}")
            return None

    def generate_client_id(self):
        """Генерация уникального ID клиента"""
        import uuid
        return str(uuid.uuid4())

    def generate_subscription_url(self, inbound, client_id):
        """Генерация ссылки для подписки"""
        try:
            # Формируем ссылку для подписки
            base_url = self.panel_url
            subscription_path = f"/sub/{inbound['id']}/{client_id}"
            subscription_url = f"{base_url}{subscription_path}"

            logger.info(f"🔗 Сгенерирована ссылка: {subscription_url}")
            return subscription_url

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ссылки: {e}")
            return f"{self.panel_url}/sub/{client_id}"

    def test_connection(self):
        """Тестирование подключения к 3x-ui"""
        logger.info("🧪 Тестирование подключения к 3x-ui...")
        if self.login():
            inbounds = self.get_inbounds()
            if inbounds:
                logger.info("✅ Подключение к 3x-ui успешно")
                return True
        logger.error("❌ Не удалось подключиться к 3x-ui")
        return False


# Инициализация менеджеров
db_manager = DatabaseManager(DB_NAME)
xui_manager = XUIManager(XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 Зарегистрироваться", callback_data="register")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я бот для создания VPN подключений\n"
        f"🔐 Зарегистрируйтесь и получите персональную ссылку\n\n"
        f"⚡ Быстро • 🔒 Безопасно • 🆓 Бесплатно"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "register":
        await register_user(query, context)
    elif query.data == "status":
        await show_status(query, context)
    elif query.data == "help":
        await help_command(query, context)


async def register_user(query, context):
    user = query.from_user

    # Проверяем, не зарегистрирован ли уже пользователь
    existing_user = db_manager.get_user(user.id)

    if existing_user:
        subscription_url = existing_user[6]
        await query.edit_message_text(
            f"✅ Вы уже зарегистрированы!\n\n"
            f"🔗 Ваша ссылка для подключения:\n"
            f"`{subscription_url}`\n\n"
            f"Используйте кнопку '📊 Мой статус' для подробной информации.",
            parse_mode='Markdown'
        )
        return

    # Запрашиваем email
    context.user_data['awaiting_email'] = True
    await query.edit_message_text(
        "📧 **Введите ваш email для регистрации:**\n\n"
        "⚠️ На этот email будет привязан ваш VPN аккаунт\n"
        "📝 Пример: user@example.com"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_email'):
        email = update.message.text.strip()
        user = update.effective_user

        # Валидация email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            await update.message.reply_text(
                "❌ **Неверный формат email!**\n\n"
                "📧 Пожалуйста, введите корректный email:\n"
                "Пример: user@example.com"
            )
            return

        # Проверяем существование пользователя
        if db_manager.get_user(user.id):
            await update.message.reply_text("❌ Вы уже зарегистрированы в системе!")
            context.user_data['awaiting_email'] = False
            return

        # Создаем клиента в существующем инбаунде
        await update.message.reply_text("⏳ **Создаем ваш VPN аккаунт...**\n\nПожалуйста, подождите ⏰")

        client_result = xui_manager.create_client(email, user.id, INBOUND_ID, DATA_LIMIT_GB)

        if client_result and client_result.get('client_id'):
            # Сохраняем пользователя в базу
            success = db_manager.add_user(
                user.id,
                user.username,
                user.full_name,
                email,
                client_result['client_id'],
                client_result['subscription_url']
            )

            if success:
                if client_result.get('existing', False):
                    message = "🔄 Найден существующий аккаунт!"
                else:
                    message = "🎉 **Регистрация успешна!**"

                await update.message.reply_text(
                    f"{message}\n\n"
                    f"👤 **Пользователь:** {user.full_name}\n"
                    f"📧 **Email:** {email}\n"
                    f"📊 **Лимит трафика:** {DATA_LIMIT_GB} GB\n\n"
                    f"🔗 **Ваша ссылка для подключения:**\n"
                    f"`{client_result['subscription_url']}`\n\n"
                    f"📱 **Как использовать:**\n"
                    f"1. Скопируйте ссылку выше\n"
                    f"2. Вставьте в ваш VPN клиент\n"
                    f"3. Активируйте подключение\n\n"
                    f"🛡️ **Приятного использования!**",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ **Ошибка сохранения данных!**\n\n"
                    "Аккаунт создан, но возникла ошибка при сохранении. "
                    "Обратитесь к администратору."
                )
        else:
            await update.message.reply_text(
                "❌ **Ошибка создания VPN аккаунта!**\n\n"
                "Возможные причины:\n"
                "• Панель 3x-ui недоступна\n"
                "• Неправильные логин/пароль\n"
                "• Инбаунд не найден\n"
                "• Технические работы\n\n"
                "Попробуйте позже или обратитесь к администратору."
            )

        context.user_data['awaiting_email'] = False


async def show_status(query, context):
    user = query.from_user
    user_data = db_manager.get_user(user.id)

    if user_data:
        _, telegram_id, username, full_name, email, xui_client_id, subscription_url, created_at = user_data

        status_text = (
            f"✅ **Ваш VPN аккаунт активен**\n\n"
            f"👤 **Имя:** {full_name or 'Не указано'}\n"
            f"📧 **Email:** {email}\n"
            f"📊 **Лимит трафика:** {DATA_LIMIT_GB} GB\n"
            f"📅 **Регистрация:** {created_at[:10]}\n"
            f"🆔 **ID клиента:** {xui_client_id}\n\n"
        )

        if subscription_url:
            status_text += f"🔗 **Ссылка для подключения:**\n`{subscription_url}`\n\n"

        status_text += "🔄 Обновите подписку в клиенте если подключение не работает"

        await query.edit_message_text(status_text, parse_mode='Markdown')
    else:
        await query.edit_message_text(
            "❌ **Вы не зарегистрированы!**\n\n"
            "Нажмите кнопку '📝 Зарегистрироваться' чтобы создать VPN аккаунт."
        )


async def help_command(query, context):
    support_mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "администратору"

    help_text = (
        "ℹ️ **Помощь по использованию бота**\n\n"
        "🔸 **Как зарегистрироваться:**\n"
        "1. Нажмите '📝 Зарегистрироваться'\n"
        "2. Введите ваш email\n"
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
        "• Без ограничения по времени\n\n"
        f"🆘 **Поддержка:** {support_mention}"
    )
    await query.edit_message_text(help_text, parse_mode='Markdown')


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестирования подключения к 3x-ui (только для админов)"""
    await update.message.reply_text("🧪 Тестируем подключение к 3x-ui...")

    if xui_manager.test_connection():
        await update.message.reply_text("✅ Подключение к 3x-ui успешно!")
    else:
        await update.message.reply_text("❌ Не удалось подключиться к 3x-ui")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)


def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск VPN Telegram бота...")
    logger.info(f"🔗 3x-ui панель: {XUI_PANEL_URL}")
    logger.info(f"📊 Лимит данных: {DATA_LIMIT_GB} GB")
    logger.info(f"🎯 Inbound ID: {INBOUND_ID}")
    logger.info(f"💾 База данных: {DB_NAME}")

    # Тестируем подключение при запуске
    logger.info("🧪 Тестируем подключение к 3x-ui...")
    if not xui_manager.test_connection():
        logger.warning("⚠️ Не удалось подключиться к 3x-ui при запуске")

    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))  # Для тестирования
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе!")
    application.run_polling()


if __name__ == '__main__':
    main()