from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Base
import os

DB_URL = os.getenv("DB_URL")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
