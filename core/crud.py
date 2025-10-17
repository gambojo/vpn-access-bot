from core.db import SessionLocal
from core.models import User, Subscription, SubscriptionLog
from datetime import datetime, timedelta

def create_or_get_user(telegram_id, username):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        db.commit()
    return user

def update_subscription(telegram_id, expires_at, uuid):
    db = SessionLocal()
    sub = db.query(Subscription).filter_by(telegram_id=telegram_id).first()
    if not sub:
        sub = Subscription(telegram_id=telegram_id)
        db.add(sub)
    sub.expires_at = expires_at
    sub.uuid = uuid
    db.add(SubscriptionLog(telegram_id=telegram_id, action="renewed"))
    db.commit()

def get_expiring_subscriptions(within_days=3):
    db = SessionLocal()
    threshold = datetime.utcnow() + timedelta(days=within_days)
    return db.query(Subscription).filter(Subscription.expires_at <= threshold).all()

def is_subscription_active(uuid):
    db = SessionLocal()
    sub = db.query(Subscription).filter_by(uuid=uuid).first()
    return sub and sub.expires_at > datetime.utcnow()

def get_filtered_subscriptions(username="", active_only=False):
    db = SessionLocal()
    query = db.query(Subscription).join(User)
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    if active_only:
        query = query.filter(Subscription.expires_at > datetime.utcnow())
    return query.all()

def renew_subscription(telegram_id):
    db = SessionLocal()
    sub = db.query(Subscription).filter_by(telegram_id=telegram_id).first()
    if sub:
        sub.expires_at = datetime.utcnow() + timedelta(days=30)
        db.add(SubscriptionLog(telegram_id=telegram_id, action="renewed"))
        db.commit()

def delete_subscription(telegram_id):
    db = SessionLocal()
    db.query(Subscription).filter_by(telegram_id=telegram_id).delete()
    db.add(SubscriptionLog(telegram_id=telegram_id, action="deleted"))
    db.commit()

def get_user_config(telegram_id):
    db = SessionLocal()
    sub = db.query(Subscription).filter_by(telegram_id=telegram_id).first()
    if sub:
        return f"vless://{sub.uuid}@193.32.177.130:443?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision#user_{telegram_id}"
    return "Конфиг не найден"
