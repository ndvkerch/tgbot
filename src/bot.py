import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from database import init_db

# Импортируем обработчики команд
from handlers.start import start_router
from handlers.checkin import checkin_router
from handlers.profile import profile_router
from handlers.spots import spots_router

# Импортируем планировщик задач
from scheduler import start_scheduler

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь .env файл.")

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Создаем бота и диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Подключаем обработчики
dp.include_router(start_router)
dp.include_router(checkin_router)
dp.include_router(profile_router)
dp.include_router(spots_router)

async def main():
    logging.info("Инициализация базы данных...")
    init_db()  # Создаем таблицы перед запуском бота
    
    logging.info("Запуск планировщика задач...")
    start_scheduler()  # Запускаем планировщик для автоматического разчекина
    
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())