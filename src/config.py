import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "data/database.db"
WINDY_API_KEY = os.getenv("WINDY_API_KEY")

if not BOT_TOKEN or not WINDY_API_KEY:
    raise ValueError("Необходимые переменные окружения (BOT_TOKEN или WINDY_API_KEY) не найдены!")