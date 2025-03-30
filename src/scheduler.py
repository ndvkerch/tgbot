import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import sqlite3

logging.basicConfig(level=logging.INFO)

DB_PATH = "data/database.db"

scheduler = AsyncIOScheduler()

def check_expired_checkins():
    """Проверяет истёкшие чек-ины и разчекивает пользователей."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            current_time = datetime.utcnow().isoformat()
            cursor.execute("""
                SELECT id, user_id, spot_id
                FROM checkins
                WHERE active = 1 AND end_time IS NOT NULL AND end_time < ?
            """, (current_time,))
            expired_checkins = cursor.fetchall()
            
            for checkin in expired_checkins:
                checkin_id, user_id, spot_id = checkin
                cursor.execute("UPDATE checkins SET active = 0 WHERE id = ?", (checkin_id,))
                logging.info(f"✅ Автоматический разчекин: пользователь {user_id} на споте {spot_id} (checkin_id={checkin_id})")
            conn.commit()
    except Exception as e:
        logging.error(f"❌ Ошибка при проверке истёкших чек-инов: {e}")

def start_scheduler():
    """Запускает планировщик задач."""
    scheduler.add_job(check_expired_checkins, "interval", seconds=60)  # Проверяем каждые 60 секунд
    scheduler.start()
    logging.info("✅ Планировщик задач запущен.")