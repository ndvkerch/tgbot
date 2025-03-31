import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from database import init_db

# Импортируем middleware
from middlewares import BotMiddleware

# Импортируем обработчики команд
from handlers.start import start_router
from handlers.checkin import checkin_router
from handlers.profile import profile_router
from handlers.spots import spots_router

# Импортируем планировщик задач
from scheduler import start_scheduler

# Блок 1: Настройка окружения и логирования
# Загружаем переменные окружения из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Проверяем наличие токена
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь .env файл.")

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Блок 2: Инициализация бота и диспетчера
# Создаём бота и диспетчер
bot = Bot(token=TOKEN)
storage = MemoryStorage()  # Используем хранилище в памяти для FSM
dp = Dispatcher(bot=bot, storage=storage)

# Регистрируем middleware для передачи объекта bot в обработчики
dp.message.middleware(BotMiddleware(bot))
dp.callback_query.middleware(BotMiddleware(bot))

# Блок 3: Подключение обработчиков
# Подключаем роутеры для обработки команд
dp.include_router(start_router)
dp.include_router(checkin_router)
dp.include_router(profile_router)
dp.include_router(spots_router)

# Блок 4: Основная функция запуска
async def main():
    """Основная функция для запуска бота."""
    logging.info("Инициализация базы данных...")
    init_db()  # Создаём таблицы перед запуском бота
    
    logging.info("Запуск планировщика задач...")
    start_scheduler(bot=bot)  # Запускаем планировщик для автоматического разчекина
    
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

# Блок 5: Точка входа
if __name__ == "__main__":
    """Точка входа для запуска бота."""
    asyncio.run(main())