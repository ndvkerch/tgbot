import math
import logging
import json
from typing import Optional, Tuple
from aiocache import Cache
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards import create_location_request_keyboard

logger = logging.getLogger(__name__)

class GeoState(StatesGroup):
    waiting_for_spots_location = State()
    waiting_for_weather_location = State()

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

cache = Cache(Cache.MEMORY)

async def get_cached_location(user_id: int) -> Optional[Tuple[float, float]]:
    key = f"location:{user_id}"
    cached_data = await cache.get(key)
    logger.debug(f"Проверка кэша для user_id={user_id}: данные={cached_data}")
    if cached_data:
        try:
            location = json.loads(cached_data)
            logger.info(f"Используется кэшированная геолокация для user_id={user_id}: {location}")
            return tuple(location)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка десериализации кэша для user_id={user_id}: {e}")
            return None
    logger.debug(f"Кэш пуст для user_id={user_id}")
    return None

async def set_cached_location(user_id: int, location: Tuple[float, float]) -> None:
    key = f"location:{user_id}"
    data = json.dumps([location[0], location[1]])
    await cache.set(key, data, ttl=600)
    logger.info(f"Геолокация сохранена в кэш для user_id={user_id}: {data}")

async def request_user_location(message: types.Message, state: FSMContext) -> Optional[Tuple[float, float]]:
    user_id = message.from_user.id
    logger.debug(f"Вызов request_user_location для user_id={user_id}, location={message.location}")

    # Проверяем кэш
    cached_location = await get_cached_location(user_id)
    if cached_location:
        logger.info(f"Используется кэшированная геолокация для user_id={user_id}: {cached_location}")
        await state.clear()
        return cached_location

    # Проверяем наличие геолокации в сообщении
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
        location = (lat, lon)
        logger.info(f"Получена новая геолокация от user_id={user_id}: {location}")
        await set_cached_location(user_id, location)
        await state.clear()
        return location

    # Запрашиваем геолокацию
    logger.info(f"Запрашиваем геолокацию у user_id={user_id}")
    await message.answer(
        "❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.",
        reply_markup=create_location_request_keyboard()
    )
    await state.set_state(GeoState.waiting_for_spots_location)
    return None