import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import aiosqlite

logging.basicConfig(level=logging.INFO)

DB_PATH = "data/database.db"

scheduler = AsyncIOScheduler()

async def check_expired_checkins(bot=None):
    """Проверяет истёкшие чек-ины, разчекивает пользователей и отправляет уведомления."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            current_time = datetime.utcnow().isoformat()
            await cursor.execute("""
                SELECT id, user_id, spot_id
                FROM checkins
                WHERE active = 1 AND end_time IS NOT NULL AND end_time < ?
            """, (current_time,))
            expired_checkins = await cursor.fetchall()
            
            for checkin in expired_checkins:
                checkin_id, user_id, spot_id = checkin
                # Разчекиниваем пользователя
                await cursor.execute("UPDATE checkins SET active = 0 WHERE id = ?", (checkin_id,))
                logging.info(f"✅ Автоматический разчекин: пользователь {user_id} на споте {spot_id} (checkin_id={checkin_id})")
                
                # Отправляем уведомление пользователю
                if bot:
                    try:
                        await cursor.execute("SELECT name FROM spots WHERE id = ?", (spot_id,))
                        spot_name = (await cursor.fetchone())[0]
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"⏰ Время вашего пребывания на споте '{spot_name}' истекло. Вы автоматически покинули спот."
                        )
                        logging.info(f"✅ Уведомление о разчекине отправлено пользователю {user_id}")
                    except Exception as e:
                        logging.error(f"❌ Ошибка при отправке уведомления пользователю {user_id}: {e}")
            await conn.commit()
    except Exception as e:
        logging.error(f"❌ Ошибка при проверке истёкших чек-инов: {e}")

def start_scheduler(bot=None):
    """Запускает планировщик задач."""
    scheduler.add_job(check_expired_checkins, "interval", seconds=300, args=[bot])  # Проверяем каждые 60 секунд
    scheduler.start()
    logging.info("✅ Планировщик задач запущен.")