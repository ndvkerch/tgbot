import aiohttp
import logging
import math
from aiocache import cached
from config import WINDY_API_KEY

logging.basicConfig(level=logging.INFO)

@cached(ttl=600)  # Кэшируем данные на 10 минут
async def get_windy_forecast(lat: float, lon: float) -> dict:
    """
    Получает прогноз ветра с Windy API по координатам спота.
    
    Args:
        lat (float): Широта спота.
        lon (float): Долгота спота.
    
    Returns:
        dict: Данные о ветре (скорость и направление) или None в случае ошибки.
    """
    url = "https://api.windy.com/api/point-forecast/v2"
    payload = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",
        "parameters": ["wind"],
        "levels": ["surface"],
        "key": WINDY_API_KEY
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logging.error(f"Ошибка Windy API: статус {response.status}, текст: {await response.text()}")
                    return None
                
                data = await response.json()
                
                # Проверка наличия ключей для компонентов ветра
                if "wind_u-surface" in data and "wind_v-surface" in data:
                    u = data["wind_u-surface"][0]  # Компонента U (восток-запад)
                    v = data["wind_v-surface"][0]  # Компонента V (север-юг)
                    
                    # Вычисление скорости ветра
                    wind_speed = math.sqrt(u**2 + v**2)
                    
                    # Вычисление направления ветра в градусах
                    wind_direction_rad = math.atan2(v, u)
                    wind_direction_deg = math.degrees(wind_direction_rad)
                    
                    # Корректировка направления для метеорологической системы (0° — север, 90° — восток)
                    wind_direction = (270 - wind_direction_deg) % 360
                    
                    return {
                        "speed": wind_speed,
                        "direction": wind_direction
                    }
                else:
                    logging.error("Неверная структура ответа от Windy API: отсутствуют wind_u-surface или wind_v-surface")
                    return None
    except Exception as e:
        logging.error(f"Ошибка при запросе к Windy API: {e}")
        return None

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра в текстовую форму (например, 'Северный')."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]