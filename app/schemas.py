from pydantic import BaseModel
from datetime import datetime

class UserCreate(BaseModel):
    telegram_id: int
    username: str

class UserRead(BaseModel):
    id: int
    telegram_id: int
    username: str
    created_at: datetime

    class Config:
        orm_mode = True
