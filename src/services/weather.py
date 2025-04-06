import aiohttp
import logging
import math
from aiocache import cached

logging.basicConfig(level=logging.INFO)

@cached(ttl=600)
async def get_open_meteo_forecast(lat: float, lon: float) -> dict:
    """
    Получает текущие данные о ветре и температуру воды с Open‑Meteo.
    
    Используются два эндпоинта:
      - Open‑Meteo API для получения текущего прогноза ветра с автоматическим определением часового пояса.
      - Open‑Meteo Marine API для получения температуры поверхности моря.
    
    Args:
        lat (float): Широта точки.
        lon (float): Долгота точки.
    
    Returns:
        dict: Словарь с данными о ветре (скорость и направление) и температуре воды (°C).
              Если данные недоступны, возвращается None.
    """
    # Эндпоинт Open‑Meteo для текущего прогноза ветра (timezone=auto для определения местного времени)
    url_wind = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&windspeed_unit=ms&timezone=auto"
    
    # Эндпоинт Open‑Meteo Marine API для температуры воды
    url_water = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=sea_surface_temperature"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Запрос для получения текущих данных о ветре
            async with session.get(url_wind) as response_wind:
                if response_wind.status != 200:
                    logging.error(f"Ошибка Open‑Meteo Wind API: {await response_wind.text()}")
                    return None
                wind_data = await response_wind.json()
                
                if "current_weather" in wind_data:
                    current = wind_data["current_weather"]
                    wind_speed = current.get("windspeed")
                    wind_direction = current.get("winddirection")
                    if wind_speed is None or wind_direction is None:
                        logging.error("Данные о ветре отсутствуют в current_weather")
                        return None
                else:
                    logging.error("Отсутствует ключ 'current_weather' в ответе Open‑Meteo")
                    return None
            
            # Запрос для получения температуры воды
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
            "water_temperature": water_temp  # None, если данные отсутствуют
        }
    except Exception as e:
        logging.error(f"Ошибка при запросе: {e}")
        return None

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра (в градусах) в текстовую форму."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]
