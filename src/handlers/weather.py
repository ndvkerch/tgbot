import logging
import math
from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz

from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_checkins_for_spot
from services.weather import get_windy_forecast, wind_direction_to_text

logging.basicConfig(level=logging.INFO)
weather_router = Router()

# Определение состояний FSM
class WeatherSpotsState(StatesGroup):
    waiting_for_location = State()

# Вспомогательная функция для вычисления расстояния
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками на Земле (в километрах)."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# Инициализация TimezoneFinder
tf = TimezoneFinder()

@weather_router.callback_query(F.data == "weather_nearby_spots")
async def request_location_for_weather_spots(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем геолокацию для поиска ближайших спотов."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.edit_text("📍 Отправьте вашу геолокацию, чтобы узнать погоду на ближайших спотах:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
    await state.set_state(WeatherSpotsState.waiting_for_location)
    await callback.answer()

@weather_router.message(WeatherSpotsState.waiting_for_location, F.location)
async def process_location_for_weather_spots(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию и показываем 5 ближайших спотов с погодой."""
    user_lat = message.location.latitude
    user_lon = message.location.longitude

    # Определяем часовой пояс
    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon) or "UTC"
    user_timezone = pytz.timezone(timezone_name)

    # Получаем все споты
    spots = await get_spots() or []
    if not spots:
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Вычисляем расстояния до всех спотов
    distances = [
        (spot, haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"]))
        for spot in spots
    ]
    # Сортируем по расстоянию и берём 5 ближайших
    nearest_spots = sorted(distances, key=lambda x: x[1])[:5]

    # Формируем ответ
    response = "🌤️ **Ближайшие споты:**\n\n"
    for spot, distance in nearest_spots:
        on_spot_count, on_spot_users, arriving_users = await get_checkins_for_spot(spot["id"])
        on_spot_names = ", ".join(user["first_name"] for user in on_spot_users) if on_spot_users else "никого"

        arriving_info = "нет"
        if arriving_users:
            arriving_info_list = []
            for user in arriving_users:
                arrival_time_str = user["arrival_time"]
                if "T" not in arrival_time_str:
                    arrival_time_str = f"{datetime.utcnow().date()}T{arrival_time_str}+00:00"
                utc_time = datetime.fromisoformat(arrival_time_str.replace("Z", "+00:00"))
                local_time = utc_time.replace(tzinfo=pytz.utc).astimezone(user_timezone)
                arriving_info_list.append(f"{user['first_name']} ({local_time.strftime('%H:%M')})")
            arriving_info = ", ".join(arriving_info_list)

        # Получаем данные о ветре и температуре воды
        wind_data = await get_windy_forecast(spot["lat"], spot["lon"])
        wind_info = "🌬 *Ветер:* Данные недоступны."
        water_info = "💧 *Вода:* Данные недоступны."
        if wind_data:
            wind_speed = wind_data["speed"]
            wind_direction = wind_data["direction"]
            direction_text = wind_direction_to_text(wind_direction)
            wind_info = f"🌬 *Ветер:* {wind_speed:.1f} м/с, {direction_text} ({wind_direction:.0f}°)"
            if "water_temperature" in wind_data and wind_data["water_temperature"] is not None:
                water_info = f"💧 *Вода:* {wind_data['water_temperature']:.1f} °C"

        response += (
            f"🏄‍♂️ **{spot['name']}**\n"
            f"📍 *Расстояние:* {distance:.2f} км\n"
            f"{wind_info}\n"
            f"{water_info}\n"
            f"👥 *На месте:* {on_spot_count} чел. ({on_spot_names})\n"
            f"⏳ *Приедут:* {len(arriving_users)} чел. ({arriving_info})\n\n"
        )

    # Клавиатура
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"plan_to_arrive_{spot['id']}")]
            for spot, distance in nearest_spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )

    await message.answer(response, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.clear()

@weather_router.message(WeatherSpotsState.waiting_for_location)
async def handle_invalid_location_for_weather_spots(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не геолокацию."""
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)