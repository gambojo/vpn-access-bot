from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    telegram_id = Column(Integer, primary_key=True)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    expires_at = Column(DateTime)
    uuid = Column(String)
    auto_renew = Column(Boolean, default=False)

class SubscriptionLog(Base):
    __tablename__ = "subscription_logs"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
