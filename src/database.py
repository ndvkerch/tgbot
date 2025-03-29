import sqlite3
import logging
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)

DB_PATH = "data/database.db"

# Проверяем, существует ли путь к БД
if not os.path.exists(DB_PATH):
    logging.warning(f"⚠️ Файл базы данных {DB_PATH} не найден!")

def init_db():
    """Создает таблицы в БД, если их нет."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )""")
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spot_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )""")
            conn.commit()
            logging.info("✅ Таблицы успешно инициализированы.")
    except Exception as e:
        logging.error(f"❌ Ошибка при инициализации БД: {e}")

def get_spots():
    """Получает список всех спотов."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, latitude, longitude FROM spots")
            spots = [{"id": row[0], "name": row[1], "lat": row[2], "lon": row[3]} for row in cursor.fetchall()]
            logging.info(f"🔍 Найдено {len(spots)} спотов в базе.")
            return spots
    except Exception as e:
        logging.error(f"❌ Ошибка при получении списка спотов: {e}")
        return []

def add_spot(name, lat, lon):
    """Добавляет новый спот в БД и возвращает его ID."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO spots (name, latitude, longitude) VALUES (?, ?, ?)", (name, lat, lon))
            conn.commit()
            spot_id = cursor.lastrowid
            logging.info(f"✅ Новый спот добавлен: ID={spot_id}, Name={name}, Lat={lat}, Lon={lon}")
            return spot_id
    except Exception as e:
        logging.error(f"❌ Ошибка при добавлении спота: {e}")
        return None

def checkin_user(user_id, spot_id):
    """Добавляет запись о чекине пользователя."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            timestamp = datetime.utcnow().isoformat()
            cursor.execute("INSERT INTO checkins (user_id, spot_id, timestamp) VALUES (?, ?, ?)", (user_id, spot_id, timestamp))
            conn.commit()
            logging.info(f"✅ Чекин пользователя {user_id} на споте {spot_id} ({timestamp})")
    except Exception as e:
        logging.error(f"❌ Ошибка при чекине пользователя: {e}")

# Инициализация БД при запуске
init_db()
