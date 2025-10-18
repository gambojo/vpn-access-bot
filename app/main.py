from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from . import crud, schemas
from .dependencies import get_db

app = FastAPI()

@app.on_event("startup")
async def startup():
    # Инициализация базы данных
    from .database import init_db
    await init_db()

@app.post("/subscribe/", response_model=schemas.UserRead)
async def subscribe(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    existing_user = await crud.get_user_by_telegram_id(db, user.telegram_id)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    new_user = await crud.create_user(db, user.dict())
    return new_user

@app.get("/users/{telegram_id}", response_model=schemas.UserRead)
async def get_user(telegram_id: int, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
