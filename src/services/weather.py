import aiohttp
import logging
import math
from aiocache import cached
from config import WINDY_API_KEY

logging.basicConfig(level=logging.INFO)

@cached(ttl=600)  # Кэшируем данные на 10 минут
async def get_windy_forecast(lat: float, lon: float) -> dict:
    """
    Получает прогноз ветра и температуры с Windy API по координатам спота.
    
    Args:
        lat (float): Широта спота.
        lon (float): Долгота спота.
    
    Returns:
        dict: Данные о ветре (скорость в м/с и направление в градусах) и температуре (в °C) или None в случае ошибки.
    """
    url = "https://api.windy.com/api/point-forecast/v2"
    payload = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",
        "parameters": ["wind", "temp"],  # Добавляем "temp" для температуры
        "levels": ["surface"],          # Уровень поверхности
        "key": WINDY_API_KEY
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logging.error(f"Ошибка Windy API: статус {response.status}, текст: {await response.text()}")
                    return None
                
                data = await response.json()
                
                # Проверка наличия всех нужных ключей
                required_keys = ["wind_u-surface", "wind_v-surface", "temp-surface"]
                if all(key in data for key in required_keys):
                    # Компоненты ветра
                    u = data["wind_u-surface"][0]  # м/с, восток-запад
                    v = data["wind_v-surface"][0]  # м/с, север-юг
                    # Температура
                    temp_kelvin = data["temp-surface"][0]  # Кельвины
                    
                    # Скорость ветра (м/с)
                    wind_speed = math.sqrt(u**2 + v**2)
                    
                    # Направление ветра (градусы)
                    wind_direction_rad = math.atan2(v, u)
                    wind_direction_deg = math.degrees(wind_direction_rad)
                    # Корректировка для метеорологической системы: 0° — север, 90° — восток
                    wind_direction = (270 - wind_direction_deg) % 360
                    
                    # Температура в Цельсиях
                    temp_celsius = temp_kelvin - 273.15
                    
                    return {
                        "speed": wind_speed,        # м/с
                        "direction": wind_direction, # градусы
                        "temperature": temp_celsius  # °C
                    }
                else:
                    missing = [key for key in required_keys if key not in data]
                    logging.error(f"Отсутствуют ключи в ответе Windy API: {missing}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка при запросе к Windy API: {e}")
        return None

def wind_direction_to_text(degrees: float) -> str:
    """Преобразует направление ветра в текстовую форму (например, 'Северный')."""
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    index = round(degrees / 45) % 8
    return directions[index]