import logging
import math
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder
import pytz

from aiogram import Router, types, F, Bot
from aiogram.types import ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_active_checkin, get_checkins_for_spot, checkin_user, get_user, add_or_update_user
from services.weather import get_open_meteo_forecast as get_windy_forecast, wind_direction_to_text
from keyboards import (
    create_location_request_keyboard,
    create_back_to_menu_keyboard,
    create_nearby_spots_keyboard,
    create_arrival_time_keyboard,
    create_confirm_arrival_keyboard,
)
from .checkin import CheckinState  # Импортируем CheckinState

logging.basicConfig(level=logging.INFO)
spots_router = Router()

class NearbySpotsState(StatesGroup):
    waiting_for_location = State()
    # setting_arrival_time больше не нужно, используем CheckinState.setting_arrival_time

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками на Земле (в километрах) с помощью формулы гаверсинуса."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

tf = TimezoneFinder()

@spots_router.callback_query(F.data == "nearby_spots")
async def request_location_for_nearby_spots(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем геолокацию для поиска ближайших спотов."""
    keyboard = create_location_request_keyboard()
    await callback.message.edit_text("📍 Отправьте вашу геолокацию, чтобы найти ближайшие споты:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
    await state.set_state(NearbySpotsState.waiting_for_location)
    await callback.answer()

@spots_router.message(NearbySpotsState.waiting_for_location, F.location)
async def process_location_for_nearby_spots(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию и показываем до 5 спотов с активными чек-инами."""
    user_id = message.from_user.id
    user_lat = message.location.latitude
    user_lon = message.location.longitude

    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon) or "UTC"
    user_timezone = pytz.timezone(timezone_name)

    user = await get_user(user_id)
    await add_or_update_user(
        user_id=user_id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
        timezone=timezone_name
    )

    spots = await get_spots() or []
    if not spots:
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = create_back_to_menu_keyboard()
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    active_spots = []
    for spot in spots:
        active_count, active_users, arriving_users = await get_checkins_for_spot(spot["id"])
        if active_count > 0 or len(arriving_users) > 0:
            distance = haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])
            active_spots.append((spot, distance))

    nearest_active_spots = sorted(active_spots, key=lambda x: x[1])[:5]

    if not nearest_active_spots:
        await message.answer(
            "🌬️🚫🔍 На спотах активность не обнаружена!\n"
            "🚗📍🤔 Собрался или приехал на спот и решил остаться?\n"
            "📢📍🤙 Дай знать — отметь себя на споте!\n"
            "🌍👥🌪️🪁 Все будут знать, где сегодня вкатывают.",
            reply_markup=ReplyKeyboardRemove()
        )
        keyboard = create_back_to_menu_keyboard()
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    response = "🔍 **Активные споты:**\n\n"
    for spot, distance in nearest_active_spots:
        active_count, active_users, arriving_users = await get_checkins_for_spot(spot["id"])
        on_spot_names = ", ".join(user["first_name"] for user in active_users) if active_users else "никого"

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
        temp_info = "🌡 *Температура:* Данные недоступны."
        if wind_data:
            wind_speed = wind_data["speed"]
            wind_direction = wind_data["direction"]
            wind_gusts = wind_data.get("gusts")
            direction_text = wind_direction_to_text(wind_direction)
            wind_info = f"🌬 *Ветер:* {wind_speed:.1f} м/с, {direction_text} ({wind_direction:.0f}°)"
            if wind_gusts is not None:
                wind_info += f", порывы до {wind_gusts:.1f} м/с"
            if "water_temperature" in wind_data and wind_data["water_temperature"] is not None:
                temp_info = f"🌡 *Вода:* {wind_data['water_temperature']:.1f} °C"

        response += (
            f"🏄‍♂️ **{spot['name']}**\n"
            f"📍 *Расстояние:* {distance:.2f} км\n"
            f"{wind_info}\n"
            f"{temp_info}\n"
            f"👥 *На месте:* {active_count} чел. ({on_spot_names})\n"
            f"⏳ *Приедут:* {len(arriving_users)} чел. ({arriving_info})\n\n"
        )

    keyboard = create_nearby_spots_keyboard(nearest_active_spots)
    await message.answer(response, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.clear()

@spots_router.message(NearbySpotsState.waiting_for_location)
async def handle_invalid_location_for_nearby_spots(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не геолокацию."""
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.")
    keyboard = create_location_request_keyboard()
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@spots_router.callback_query(F.data.startswith("arrival_"), CheckinState.setting_arrival_time)
async def process_arrival_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем время прибытия и регистрируем чек-ин."""
    arrival_str = callback.data.split("_")[1]
    now = datetime.utcnow().replace(tzinfo=pytz.utc)

    if arrival_str in ["1", "2", "3"]:
        arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()
    else:
        try:
            target_hour, target_minute = map(int, arrival_str.split(":"))
        except ValueError:
            await callback.answer("❌ Некорректный формат времени. Используйте ЧЧ:ММ (например, 21:47).")
            return

        target_time = datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=target_hour,
            minute=target_minute,
            tzinfo=pytz.utc
        ).replace(tzinfo=pytz.utc)
        if target_time < now:
            target_time += timedelta(days=1)
        arrival_time = target_time.isoformat()

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    await checkin_user(user_id, spot_id, checkin_type=2, arrival_time=arrival_time)
    spot = await get_spot_by_id(spot_id)
    await callback.message.edit_text(f"✅ Вы запланировали приезд на спот '{spot['name']}'! 🌊")

    keyboard = create_confirm_arrival_keyboard()
    await callback.message.answer("Когда приедете, подтвердите прибытие:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@spots_router.callback_query(F.data == "cancel_checkin", CheckinState.setting_arrival_time)
async def cancel_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Отмена планирования приезда."""
    await callback.message.edit_text("❌ Планирование приезда отменено.")
    keyboard = create_back_to_menu_keyboard()
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()