from apscheduler.schedulers.background import BackgroundScheduler
from core.crud import get_expiring_subscriptions
from telegram import Bot

def start_scheduler(bot: Bot):
    def notify_expiring():
        users = get_expiring_subscriptions(within_days=3)
        for user in users:
            bot.send_message(chat_id=user.telegram_id, text="🔔 Ваша VPN-подписка истекает через 3 дня!")

    scheduler = BackgroundScheduler()
    scheduler.add_job(notify_expiring, 'interval', hours=24)
    scheduler.start()
