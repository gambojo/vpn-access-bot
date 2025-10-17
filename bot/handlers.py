from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
from core.crud import create_or_get_user, update_subscription
from core.v2ray_api import create_v2ray_client

menu = ReplyKeyboardMarkup(
    [["📅 Подписка на месяц", "📆 Подписка на 3 месяца"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите срок подписки:", reply_markup=menu)

async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    text = update.message.text

    duration = timedelta(days=30) if "месяц" in text else timedelta(days=90)
    expires_at = datetime.utcnow() + duration

    user = create_or_get_user(user_id, username)
    client_config = create_v2ray_client(user_id, expires_at)
    update_subscription(user_id, expires_at, client_config["uuid"])

    await update.message.reply_text(
        f"✅ Подписка активна до {expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\nВот ваш конфиг:\n{client_config['config']}"
    )
