from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from core.crud import get_filtered_subscriptions, renew_subscription, delete_subscription, get_user_config
from telegram import Bot
from dotenv import load_dotenv
import os, secrets

load_dotenv()
router = APIRouter()
templates = Jinja2Templates(directory="admin/templates")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "vpn123")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TELEGRAM_TOKEN)

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, ADMIN_USER) and
            secrets.compare_digest(credentials.password, ADMIN_PASS)):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.username

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, username: str = "", active_only: bool = False, auth: str = Depends(check_auth)):
    subs = get_filtered_subscriptions(username=username, active_only=active_only)
    return templates.TemplateResponse("dashboard.html", {"request": request, "subs": subs})

@router.post("/admin/renew/{telegram_id}")
def renew(telegram_id: int, auth: str = Depends(check_auth)):
    renew_subscription(telegram_id)
    return {"status": "ok"}

@router.post("/admin/delete/{telegram_id}")
def delete(telegram_id: int, auth: str = Depends(check_auth)):
    delete_subscription(telegram_id)
    return {"status": "ok"}

@router.post("/admin/send/{telegram_id}")
def send_config(telegram_id: int, auth: str = Depends(check_auth)):
    config = get_user_config(telegram_id)
    bot.send_message(chat_id=telegram_id, text=f"🔐 Ваш VPN конфиг:\n{config}")
    return {"status": "sent"}

@router.get("/admin/stats")
def stats(auth: str = Depends(check_auth)):
    from core.db import SessionLocal
    from core.models import Subscription
    db = SessionLocal()
    result = db.query(Subscription.expires_at).all()
    buckets = {}
    for r in result:
        day = r[0].date().isoformat()
        buckets[day] = buckets.get(day, 0) + 1
    labels = sorted(buckets.keys())
    counts = [buckets[k] for k in labels]
    return {"labels": labels, "counts": counts}
