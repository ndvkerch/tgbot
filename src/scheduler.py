import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import aiosqlite
import subprocess
import os
import hashlib
from dotenv import load_dotenv  # Импортируем для работы с .env

# Загружаем переменные из файла .env
load_dotenv()

logging.basicConfig(level=logging.INFO)

DB_PATH = "data/database.db"

# Получаем токен из переменной окружения
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    logging.error("❌ Переменная окружения GITHUB_TOKEN не установлена в файле .env. Укажи токен для доступа к GitHub.")
    raise EnvironmentError("GITHUB_TOKEN не установлен")

# Настройки репозитория
GITHUB_USERNAME = "ndvkerch"  # Замени на своё имя пользователя GitHub
REPO_NAME = "tgbot"  # Замени на название репозитория
REPO_URL = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{REPO_NAME}.git"

scheduler = AsyncIOScheduler()

# Храним хэш файла для проверки изменений
last_db_hash = None

def get_file_hash(file_path: str) -> str:
    """Вычисляет хэш файла для проверки изменений."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

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

async def push_database_to_github():
    """Проверяет изменения в базе данных и отправляет их в GitHub."""
    global last_db_hash
    try:
        # Проверяем, существует ли файл базы данных
        if not os.path.exists(DB_PATH):
            logging.error(f"❌ Файл базы данных {DB_PATH} не найден.")
            return

        # Вычисляем текущий хэш файла
        current_hash = get_file_hash(DB_PATH)

        # Если хэш не изменился, пропускаем
        if last_db_hash == current_hash:
            logging.info("ℹ️ База данных не изменилась, пропускаем коммит.")
            return

        # Обновляем последний хэш
        last_db_hash = current_hash

        # Выполняем Git-команды
        try:
            # Настраиваем URL репозитория с токеном
            subprocess.run(["git", "remote", "set-url", "origin", REPO_URL], check=True)
            logging.info("✅ URL репозитория настроен с использованием токена.")

            # Добавляем файл в индекс
            subprocess.run(["git", "add", DB_PATH], check=True)
            logging.info(f"✅ Файл {DB_PATH} добавлен в индекс Git.")

            # Проверяем, есть ли изменения для коммита
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if not status.stdout:
                logging.info("ℹ️ Нет изменений для коммита.")
                return

            # Коммитим изменения
            commit_message = f"Автоматическое обновление базы данных: {datetime.utcnow().isoformat()}"
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            logging.info(f"✅ Создан коммит: {commit_message}")

            # Пушим изменения в репозиторий
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            logging.info("✅ Изменения успешно отправлены в GitHub.")

        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Ошибка при выполнении Git-команды: {e}")
        except Exception as e:
            logging.error(f"❌ Неизвестная ошибка при работе с Git: {e}")

    except Exception as e:
        logging.error(f"❌ Ошибка при отправке базы данных в GitHub: {e}")

def start_scheduler(bot=None):
    """Запускает планировщик задач."""
    # Проверяем истёкшие чек-ины каждые 5 минут
    scheduler.add_job(check_expired_checkins, "interval", seconds=300, args=[bot])
    
    # Отправляем базу данных в GitHub каждые 15 минут
    scheduler.add_job(push_database_to_github, "interval", seconds=900)
    
    scheduler.start()
    logging.info("✅ Планировщик задач запущен.")