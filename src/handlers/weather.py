# weather.py
import logging
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder
import pytz
from typing import Tuple

from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_checkins_for_spot, checkin_user
from services.weather import get_open_meteo_forecast as get_windy_forecast, wind_direction_to_text
from utils.geo import request_user_location, haversine_distance, GeoState
from keyboards import create_location_request_keyboard

logger = logging.getLogger(__name__)
weather_router = Router()

tf = TimezoneFinder()

def create_arrival_time_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора времени прибытия."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 1 час", callback_data="arrival_1"),
         InlineKeyboardButton(text="Через 2 часа", callback_data="arrival_2"),
         InlineKeyboardButton(text="Через 3 часа", callback_data="arrival_3")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])

class WeatherSpotsState(StatesGroup):
    setting_arrival_time = State()

@weather_router.callback_query(F.data == "weather_nearby_spots")
async def request_location_for_weather_spots(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cached_location = await get_cached_location(user_id)
    if cached_location:
        logger.info(f"Используется кэш для weather_nearby_spots user_id={user_id}: {cached_location}")
        await process_location_for_weather_spots_manual(callback.message, state, cached_location)
        await callback.answer()
        return
    await callback.message.edit_text("📍 Отправьте вашу геолокацию, чтобы узнать погоду на ближайших спотах:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=create_location_request_keyboard())
    await state.set_state(GeoState.waiting_for_weather_location)
    await callback.answer()

@weather_router.message(GeoState.waiting_for_weather_location, F.location)
async def process_location_for_weather_spots_manual(message: types.Message, state: FSMContext, location: Tuple[float, float]):
    user_lat, user_lon = location
    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon) or "UTC"
    user_timezone = pytz.timezone(timezone_name)

    spots = await get_spots() or []
    if not spots:
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    distances = [(spot, haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])) for spot in spots]
    nearest_spots = sorted(distances, key=lambda x: x[1])[:5]

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

        wind_data = await get_windy_forecast(spot["lat"], spot["lon"])
        wind_info = "🌬 *Ветер:* Данные недоступны."
        water_info = "🌡 *Вода:* Данные недоступны."
        if wind_data:
            wind_speed = wind_data["speed"]
            wind_direction = wind_data["direction"]
            wind_gusts = wind_data.get("gusts")
            direction_text = wind_direction_to_text(wind_direction)
            wind_info = f"🌬 *Ветер:* {wind_speed:.1f} м/с, {direction_text} ({wind_direction:.0f}°)"
            if wind_gusts is not None:
                wind_info += f", порывы до {wind_gusts:.1f} м/с"
            if "water_temperature" in wind_data and wind_data["water_temperature"] is not None:
                water_info = f"🌡 *Вода:* {wind_data['water_temperature']:.1f} °C"

        response += (
            f"🏄‍♂️ **{spot['name']}**\n"
            f"📍 *Расстояние:* {distance:.2f} км\n"
            f"{wind_info}\n"
            f"{water_info}\n"
            f"👥 *На месте:* {on_spot_count} чел. ({on_spot_names})\n"
            f"⏳ *Приедут:* {len(arriving_users)} чел. ({arriving_info})\n\n"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"weather_plan_to_arrive_{spot['id']}")]
            for spot, distance in nearest_spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )

    await message.answer(response, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.clear()

@weather_router.callback_query(F.data.startswith("weather_plan_to_arrive_"))
async def weather_plan_to_arrive(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем время прибытия после выбора спота в weather_router."""
    spot_id = int(callback.data.split("_")[-1])
    spot = await get_spot_by_id(spot_id)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return

    await state.update_data(spot_id=spot_id)
    await callback.message.edit_text(f"Вы выбрали спот: {spot['name']}\nКогда вы планируете приехать?")
    keyboard = create_arrival_time_keyboard()
    await callback.message.answer("Выберите время прибытия:", reply_markup=keyboard)
    await state.set_state(WeatherSpotsState.setting_arrival_time)
    await callback.answer()

@weather_router.callback_query(F.data.startswith("arrival_"), WeatherSpotsState.setting_arrival_time)
async def weather_process_arrival_time(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатываем время прибытия и регистрируем чек-ин в weather_router."""
    arrival_str = callback.data.split("_")[1]
    now = datetime.utcnow().replace(tzinfo=pytz.utc)

    if arrival_str in ["1", "2", "3"]:
        arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()
    else:
        await callback.answer("❌ Некорректный формат времени.")
        return

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    await checkin_user(user_id, spot_id, checkin_type=2, arrival_time=arrival_time)
    spot = await get_spot_by_id(spot_id)
    await callback.message.edit_text(f"✅ Вы запланировали приезд на спот '{spot['name']}'! 🌊")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я приехал!", callback_data="confirm_arrival")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.answer("Когда приедете, подтвердите прибытие:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@weather_router.callback_query(F.data == "cancel_checkin", WeatherSpotsState.setting_arrival_time)
async def weather_cancel_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Отмена планирования приезда в weather_router."""
    await callback.message.edit_text("❌ Планирование приезда отменено.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()