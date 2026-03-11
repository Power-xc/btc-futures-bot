import os
from dotenv import load_dotenv

load_dotenv()

def get_api_credentials():
    return {
        "api_key":    os.getenv("BINANCE_API_KEY", ""),
        "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    }

def is_testnet() -> bool:
    return os.getenv("USE_TESTNET", "true").lower() == "true"

def get_telegram_credentials():
    return {
        "token":     os.getenv("TELEGRAM_TOKEN", ""),
        "chat_id":   os.getenv("TELEGRAM_CHAT_ID", ""),
        "chat_id_2": os.getenv("TELEGRAM_CHAT_ID_2", ""),
    }
