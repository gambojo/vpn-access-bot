from fastapi import APIRouter, Request
import hashlib, hmac, os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

def check_auth(data: dict) -> bool:
    auth_data = {k: v for k, v in data.items() if k != 'hash'}
    sorted_data = sorted([f"{k}={v}" for k, v in auth_data.items()])
    data_check_string = "\n".join(sorted_data)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    h = hmac.new(secret_key.encode(), data_check_string.encode(), hashlib.sha256)
    return h.hexdigest() == data['hash']

@router.post("/auth")
async def telegram_auth(request: Request):
    form = await request.form()
    data = dict(form)
    if check_auth(data):
        return {"status": "ok", "telegram_id": str(data["id"]), "username": data["username"]}
    return {"status": "error", "message": "Invalid auth"}
