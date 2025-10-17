import os
import requests
from dotenv import load_dotenv
load_dotenv()

API_URL = os.getenv("V2RAY_API_URL")
USERNAME = os.getenv("V2RAY_API_USERNAME")
PASSWORD = os.getenv("V2RAY_API_PASSWORD")

session = requests.Session()

def login():
    response = session.post(f"{API_URL}/login", json={"username": USERNAME, "password": PASSWORD}, verify=False)
    if response.status_code != 200:
        raise Exception("Ошибка авторизации в 3X-UI API")

def create_v2ray_client(telegram_id, expires_at):
    login()
    payload = {
        "remark": f"user_{telegram_id}",
        "enable": True,
        "expiryTime": int(expires_at.timestamp()),
        "protocol": "vless",
        "flow": "xtls-rprx-vision",
        "port": 443,
        "uuid": "auto"
    }
    response = session.post(f"{API_URL}/inbounds/add", json=payload, verify=False)
    data = response.json()
    return {
        "uuid": data["uuid"],
        "config": f"vless://{data['uuid']}@193.32.177.130:443?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision#user_{telegram_id}"
    }
