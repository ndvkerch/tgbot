import aiohttp
import logging
import math
from aiocache import cached

logging.basicConfig(level=logging.INFO)

@cached(ttl=600)
async def get_open_meteo_forecast(lat: float, lon: float) -> dict:
    """
    Получает текущие данные о ветре, порывах ветра и температуре воды с Open‑Meteo.
    
    Используются два эндпоинта:
      - Open‑Meteo API для текущего прогноза ветра и порывов с автоматическим определением часового пояса.
      - Open‑Meteo Marine API для температуры поверхности моря.
    
    Args:
        lat (float): Широта точки.
        lon (float): Долгота точки.
    
    Returns:
        dict: Словарь с данными о ветре (скорость, направление, порывы) и температуре воды (°C).
              Если данные недоступны, возвращается None.
    """
    # Исправленный URL: все параметры в current
    url_wind = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=windspeed_10m,winddirection_10m,windgusts_10m&windspeed_unit=ms&timezone=auto"
    
    url_water = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=sea_surface_temperature"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_wind) as response_wind:
                if response_wind.status != 200:
                    logging.error(f"Ошибка Open‑Meteo Wind API: {await response_wind.text()}")
                    return None
                wind_data = await response_wind.json()
                
                # Исправляем ключ на "current" вместо "current_weather"
                if "current" in wind_data:
                    current = wind_data["current"]
                    wind_speed = current.get("windspeed_10m")
                    wind_direction = current.get("winddirection_10m")
                    wind_gusts = current.get("windgusts_10m")
                    if wind_speed is None or wind_direction is None:
                        logging.error("Данные о ветре отсутствуют в current")
                        return None
                else:
                    logging.error("Отсутствует ключ 'current' в ответе Open‑Meteo")
                    return None
            
            async with session.get(url_water) as response_water:
                if response_water.status != 200:
                    logging.error(f"Ошибка Open‑Meteo Marine API: {await response_water.text()}")
                    water_temp = None
                else:
                    water_data = await response_water.json()
                    try:
                        water_temp = water_data["hourly"]["sea_surface_temperature"][0]
                    except (KeyError, IndexError):
                        logging.warning("Температура воды недоступна")
                        water_temp = None

        return {
            "speed": wind_speed,
            "direction": wind_direction,
            "gusts": wind_gusts,
            "water_temperature": water_temp
        }
    except Exception as e:
        logging.error(f"Ошибка при запросе: {e}")
        return None

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра (в градусах) в текстовую форму."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]
