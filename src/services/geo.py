import logging
from datetime import datetime, timedelta
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram import Bot
from typing import Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кеш для хранения геоданных пользователей: {user_id: (lat, lon, timestamp)}
geo_cache: Dict[int, Tuple[float, float, datetime]] = {}

class GeoService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def get_user_location(
        self, 
        message: Message, 
        cache_timeout: int = 600  # 10 минут
    ) -> Optional[Tuple[float, float]]:
        """Запрашивает геолокацию с кешированием."""
        user_id = message.from_user.id

        # Проверка кеша
        if user_id in geo_cache:
            lat, lon, timestamp = geo_cache[user_id]
            if (datetime.now() - timestamp).total_seconds() < cache_timeout:
                logger.info(f"Используются кешированные координаты для {user_id}")
                return (lat, lon)

        # Запрос новой геолокации
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer("Пожалуйста, отправьте вашу геолокацию:", reply_markup=keyboard)
        return None

    def update_cache(self, user_id: int, lat: float, lon: float) -> None:
        """Обновляет кеш геоданных."""
        geo_cache[user_id] = (lat, lon, datetime.now())
        logger.info(f"Кеш обновлен для пользователя {user_id}")

    @staticmethod
    def calculate_distance(
        lat1: float, 
        lon1: float, 
        lat2: float, 
        lon2: float
    ) -> float:
        """Вычисляет расстояние между двумя точками (в км)."""
        # Реализация формулы Хаверсина
        from math import radians, sin, cos, sqrt, atan2
        R = 6371.0  # Радиус Земли

        lat1, lon1 = radians(lat1), radians(lon1)
        lat2, lon2 = radians(lat2), radians(lon2)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    async def get_nearest_spots(
        self,
        user_lat: float,
        user_lon: float,
        max_distance: float = 5.0  # Макс. расстояние в км
    ) -> list:
        """Возвращает список ближайших спотов."""
        from database import get_spots  # Импорт с учетом циклических зависимостей

        spots = await get_spots()
        nearest = []

        for spot in spots:
            distance = self.calculate_distance(
                user_lat, user_lon,
                spot["lat"], spot["lon"]
            )
            if distance <= max_distance:
                nearest.append((spot, distance))

        return sorted(nearest, key=lambda x: x[1])