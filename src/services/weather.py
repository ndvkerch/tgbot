import aiohttp
import logging
import math
from aiocache import cached
from config import WINDY_API_KEY

logging.basicConfig(level=logging.INFO)

@cached(ttl=600)
async def get_windy_forecast(lat: float, lon: float) -> dict:
    """
    Получает прогноз ветра с Windy API и температуру воды с Open-Meteo.
    
    Args:
        lat (float): Широта спота.
        lon (float): Долгота спота.
    
    Returns:
        dict: Данные о ветре (скорость и направление) и температуре воды (°C).
    """
    # Windy API для ветра
    url_windy = "https://api.windy.com/api/point-forecast/v2"
    payload_windy = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",
        "parameters": ["wind"],
        "levels": ["surface"],
        "key": "heFO2edu6fB07DR8Rk94Hu1MDc5XSQH2"
    }
    
    # Open-Meteo для температуры воды
    url_openmeteo = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=sea_surface_temperature"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Запрос к Windy для ветра
            async with session.post(url_windy, json=payload_windy) as response_windy:
                if response_windy.status != 200:
                    logging.error(f"Ошибка Windy API: {await response_windy.text()}")
                    return None
                windy_data = await response_windy.json()
                
                if "wind_u-surface" in windy_data and "wind_v-surface" in windy_data:
                    u = windy_data["wind_u-surface"][0]
                    v = windy_data["wind_v-surface"][0]
                    wind_speed = math.sqrt(u**2 + v**2)
                    wind_direction_rad = math.atan2(v, u)
                    wind_direction_deg = math.degrees(wind_direction_rad)
                    wind_direction = (270 - wind_direction_deg) % 360
                else:
                    logging.error("Отсутствуют данные о ветре")
                    return None

            # Запрос к Open-Meteo для температуры воды
            async with session.get(url_openmeteo) as response_openmeteo:
                if response_openmeteo.status != 200:
                    logging.error(f"Ошибка Open-Meteo API: {await response_openmeteo.text()}")
                    return None
                openmeteo_data = await response_openmeteo.json()
                water_temp = openmeteo_data["hourly"]["sea_surface_temperature"][0]
                if water_temp is None:
                    logging.warning(f"Температура воды недоступна для ({lat}, {lon})")

        return {
            "speed": wind_speed,
            "direction": wind_direction,
            "water_temperature": water_temp  # None, если данные отсутствуют
        }
    except Exception as e:
        logging.error(f"Ошибка при запросе: {e}")
        return None

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра в текстовую форму."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]