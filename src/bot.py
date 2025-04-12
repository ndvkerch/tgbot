import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Импорты ваших модулей
from database import init_db
from middlewares import BotMiddleware
from handlers.start import start_router
from handlers.checkin import checkin_router
from handlers.profile import profile_router
from handlers.spots import spots_router
from handlers.weather import weather_router
from scheduler import start_scheduler, scheduler
from utils.geo import GeoState  # Добавлен импорт GeoState

# Настройки
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверь .env файл.")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger(__name__)

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

# Игнорируем события от самого бота
@dp.message(lambda message: message.from_user.id == bot.id)
@dp.callback_query(lambda callback: callback.from_user.id == bot.id)
async def ignore_bot_events(event):
    logger.debug(f"Игнорируем событие от бота: {event}")

# Игнорируем геолокацию вне состояний
@dp.message(F.location, ~StateFilter(GeoState.waiting_for_spots_location, GeoState.waiting_for_weather_location))
async def handle_global_location(message: types.Message):
    logger.debug(f"Игнорируем геолокацию вне состояний для user_id={message.from_user.id}")

async def main():
    # Инициализация БД
    await init_db()
    
    # Запуск планировщика
    start_scheduler(bot=bot)
    
    try:
        # Запускаем бота
        logger.info("Бот запущен")
        await dp.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Получен сигнал остановки, завершаем работу...")
    finally:
        # Останавливаем планировщик
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Планировщик остановлен")
        
        # Закрываем соединение с ботом
        await bot.session.close()
        logger.info("Сессия бота закрыта")
        
        # Закрываем хранилище FSM
        await storage.close()
        logger.info("Хранилище FSM закрыто")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")