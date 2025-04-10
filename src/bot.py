import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web  # <-- Добавляем веб-сервер

# Импорты ваших модулей
from database import init_db
from middlewares import BotMiddleware
from handlers.start import start_router
from handlers.checkin import checkin_router
from handlers.profile import profile_router
from handlers.spots import spots_router
from handlers.weather import weather_router
from scheduler import start_scheduler

# Настройки
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь .env файл.")
logging.basicConfig(level=logging.INFO)

# Создаем веб-приложение для healthcheck
async def healthcheck(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get("/health", healthcheck)

# Инициализация бота
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)
dp.message.middleware(BotMiddleware(bot))
dp.callback_query.middleware(BotMiddleware(bot))

# Подключаем роутеры
dp.include_router(start_router)
dp.include_router(checkin_router)
dp.include_router(profile_router)
dp.include_router(spots_router)
dp.include_router(weather_router)

async def main():
    # Инициализация БД
    await init_db()
    
    # Запуск планировщика
    start_scheduler(bot=bot)
    
    # Создаем фоновую задачу для веб-сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=30000)  # <-- Сервер на порту 30000
    await site.start()
    
    # Запускаем бота
    logging.info("Бот и веб-сервер запущены")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())