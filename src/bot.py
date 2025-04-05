import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from database import init_db  # Импортируем init_db

# Импортируем middleware
from middlewares import BotMiddleware

# Импортируем обработчики команд
from handlers.start import start_router
from handlers.checkin import checkin_router
from handlers.profile import profile_router
from handlers.spots import spots_router
from handlers.weather import weather_router

# Импортируем планировщик задач
from scheduler import start_scheduler

# Блок 1: Настройка окружения и логирования
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь .env файл.")
logging.basicConfig(level=logging.INFO)

# Блок 2: Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)
dp.message.middleware(BotMiddleware(bot))
dp.callback_query.middleware(BotMiddleware(bot))

# Блок 3: Подключение обработчиков
dp.include_router(start_router)
dp.include_router(checkin_router)
dp.include_router(profile_router)
dp.include_router(spots_router)
dp.include_router(weather_router)

# Блок 4: Основная функция запуска
async def main():
    """Основная функция для запуска бота."""
    logging.info("Инициализация базы данных...")
    await init_db()  # Асинхронный вызов init_db
    
    logging.info("Запуск планировщика задач...")
    start_scheduler(bot=bot)
    
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

# Блок 5: Точка входа
if __name__ == "__main__":
    """Точка входа для запуска бота."""
    asyncio.run(main())