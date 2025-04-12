import aiohttp
import logging
import math
from datetime import datetime
import asyncio  # Добавлен импорт asyncio
from aiocache import Cache, cached
from typing import Optional, Dict

logger = logging.getLogger(__name__)
cache = Cache(Cache.MEMORY)

@cached(ttl=1800, key_builder=lambda *args, **kwargs: f"wind_{args[0]}_{args[1]}")
async def get_wind_data(lat: float, lon: float) -> Optional[Dict]:
    """Получает данные о ветре с Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current=windspeed_10m,winddirection_10m,windgusts_10m&"
        f"windspeed_unit=ms&timezone=auto"
    )
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Ошибка Open-Meteo Wind API: status={response.status}")
                    return None
                data = await response.json()
                if "current" not in data:
                    logger.error("Отсутствует ключ 'current' в ответе Open-Meteo")
                    return None
                current = data["current"]
                wind_speed = current.get("windspeed_10m")
                wind_direction = current.get("winddirection_10m")
                wind_gusts = current.get("windgusts_10m")
                if wind_speed is None or wind_direction is None:
                    logger.error("Данные о ветре отсутствуют в current")
                    return None
                logger.info(f"Данные о ветре получены для lat={lat}, lon={lon}")
                return {
                    "speed": wind_speed,
                    "direction": wind_direction,
                    "gusts": wind_gusts
                }
    except Exception as e:
        logger.error(f"Ошибка при запросе ветра: {e}")
        return None

@cached(ttl=3600, key_builder=lambda *args, **kwargs: f"water_{args[0]}_{args[1]}")
async def get_water_temp(lat: float, lon: float) -> Optional[float]:
    """Получает температуру воды с Open-Meteo Marine API."""
    url = (
        f"https://marine-api.open-meteo.com/v1/marine?"
        f"latitude={lat}&longitude={lon}&hourly=sea_surface_temperature"
    )
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Ошибка Open-Meteo Marine API: status={response.status}")
                    return None
                data = await response.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("sea_surface_temperature", [])
                if not times or not temps:
                    logger.warning(f"Температура воды недоступна для lat={lat}, lon={lon}")
                    return None
                # Найти ближайшее время
                current_time = datetime.utcnow().timestamp()
                index = min(
                    range(len(times)),
                    key=lambda i: abs(
                        datetime.fromisoformat(times[i].replace("Z", "+00:00")).timestamp() - current_time
                    )
                )
                water_temp = temps[index]
                logger.info(f"Температура воды получена для lat={lat}, lon={lon}: {water_temp}°C")
                return water_temp
    except Exception as e:
        logger.error(f"Ошибка при запросе температуры воды: {e}")
        return None

async def get_open_meteo_forecast(lat: float, lon: float) -> dict:
    """
    Получает текущие данные о ветре, порывах ветра и температуре воды с Open-Meteo.

    Args:
        lat (float): Широта точки.
        lon (float): Долгота точки.

    Returns:
        dict: Словарь с данными о ветре (скорость, направление, порывы) и температуре воды (°C).
              Если данные недоступны, возвращаются значения None.
    """
    # Параллельный запуск запросов
    wind_task, water_task = await asyncio.gather(
        get_wind_data(lat, lon),
        get_water_temp(lat, lon),
        return_exceptions=True
    )

    # Обработка результатов
    result = {"speed": None, "direction": None, "gusts": None, "water_temperature": None}
    if isinstance(wind_task, dict):
        result.update(wind_task)
    elif wind_task is not None:
        logger.error(f"Ошибка в wind_task: {wind_task}")
    if isinstance(water_task, float):
        result["water_temperature"] = water_task
    elif water_task is not None:
        logger.error(f"Ошибка в water_task: {water_task}")

    return result

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра (в градусах) в текстовую форму."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]