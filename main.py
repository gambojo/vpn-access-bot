from fastapi import FastAPI
from admin.dashboard import router as admin_router
from bot.access_check import app as access_app
from auth.auth import router as auth_router

app = FastAPI()
app.mount("/check-access", access_app)
app.include_router(auth_router)
app.include_router(admin_router)
