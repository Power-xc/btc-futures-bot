import os
from dotenv import load_dotenv

load_dotenv()

def get_api_credentials():
    return {
        "api_key":    os.getenv("BINANCE_API_KEY", ""),
        "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    }

def get_telegram_credentials():
    return {
        "token":   os.getenv("TELEGRAM_TOKEN", ""),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    }
