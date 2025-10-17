from fastapi import FastAPI
from core.crud import is_subscription_active

app = FastAPI()

@app.get("/check-access/{uuid}")
def check_access(uuid: str):
    return {"active": is_subscription_active(uuid)}
