import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
DB_PATH = "data/database.db"
WINDY_API_KEY = os.getenv("WINDY_API_KEY")
