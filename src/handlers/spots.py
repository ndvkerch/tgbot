import logging
import asyncio
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder
import pytz
from typing import Tuple

from aiogram import Router, types, F, Bot
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_checkins_for_spot, checkin_user, add_or_update_user
from services.weather import get_open_meteo_forecast as get_windy_forecast, wind_direction_to_text
from utils.geo import request_user_location, haversine_distance, GeoState, get_cached_location
from keyboards import create_location_request_keyboard, create_arrival_time_keyboard

logger = logging.getLogger(__name__)
spots_router = Router()

tf = TimezoneFinder()

class NearbySpotsState(StatesGroup):
    setting_arrival_time = State()

@spots_router.callback_query(F.data == "active_spots")
async def request_location_for_active_spots(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для команды 'active_spots'. Использует кэш геолокации, если он есть."""
    user_id = callback.from_user.id
    logger.info(f"Команда active_spots вызвана для user_id={user_id}")
    cached_location = await get_cached_location(user_id)
    if cached_location:
        logger.info(f"Используется кэш для active_spots user_id={user_id}: {cached_location}")
        await state.update_data(callback_data="active_spots")
        await process_location_for_spots_manual(callback.message, state, cached_location, user_id)
        await callback.answer()
        return
    await callback.message.edit_text("📍 Отправьте вашу геолокацию, чтобы найти активные споты:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=create_location_request_keyboard())
    await state.set_state(GeoState.waiting_for_spots_location)
    await state.update_data(callback_data="active_spots")  # Сохраняем после установки состояния
    logger.debug(f"Установлено состояние GeoState.waiting_for_spots_location для user_id={user_id}, данные: {await state.get_data()}")
    await callback.answer()

@spots_router.callback_query(F.data == "nearby_spots")
async def request_location_for_nearby_spots(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для команды 'nearby_spots'. Использует кэш геолокации, если он есть."""
    user_id = callback.from_user.id
    logger.info(f"Команда nearby_spots вызвана для user_id={user_id}")
    cached_location = await get_cached_location(user_id)
    if cached_location:
        logger.info(f"Используется кэш для nearby_spots user_id={user_id}: {cached_location}")
        await state.update_data(callback_data="nearby_spots")
        await process_location_for_spots_manual(callback.message, state, cached_location, user_id)
        await callback.answer()
        return
    await callback.message.edit_text("📍 Отправьте вашу геолокацию, чтобы найти ближайшие споты:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=create_location_request_keyboard())
    await state.set_state(GeoState.waiting_for_spots_location)
    await state.update_data(callback_data="nearby_spots")  # Сохраняем после установки состояния
    logger.debug(f"Установлено состояние GeoState.waiting_for_spots_location для user_id={user_id}, данные: {await state.get_data()}")
    await callback.answer()

@spots_router.message(GeoState.waiting_for_spots_location, F.location)
async def process_location_for_spots(message: types.Message, state: FSMContext):
    """Обработчик геолокации для состояния waiting_for_spots_location."""
    user_id = message.from_user.id
    logger.info(f"Обработка геолокации для user_id={user_id}")
    data = await state.get_data()
    callback_data = data.get("callback_data")
    logger.debug(f"Состояние FSM: {await state.get_state()}, данные: {data}")
    if not callback_data:
        logger.error(f"callback_data отсутствует для user_id={user_id}, устанавливаем active_spots")
        callback_data = "active_spots"
        await state.update_data(callback_data=callback_data)
    location = await request_user_location(message, state)
    if not location:
        logger.debug(f"Геолокация не получена для user_id={user_id}")
        return
    await state.update_data(callback_data=callback_data)  # Пересохраняем перед вызовом
    await process_location_for_spots_manual(message, state, location, user_id)

async def process_location_for_spots_manual(message: types.Message, state: FSMContext, location: Tuple[float, float], user_id: int):
    """Обработка геолокации для поиска спотов (ручная, для кэша или новой геолокации)."""
    user_lat, user_lon = location
    data = await state.get_data()
    callback_data = data.get("callback_data", "active_spots")
    logger.info(f"Обработка команды с callback_data={callback_data} для user_id={user_id}")

    # Определяем часовой пояс пользователя
    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon) or "UTC"
    user_timezone = pytz.timezone(timezone_name)

    # Обновляем данные пользователя
    await add_or_update_user(
        user_id=user_id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
        timezone=timezone_name
    )

    # Получаем список спотов
    spots = await get_spots() or []
    if not spots:
        logger.warning(f"Споты не найдены для user_id={user_id}")
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Логика для active_spots
    if callback_data == "active_spots":
        active_spots = []
        for spot in spots:
            active_count, active_users, arriving_users = await get_checkins_for_spot(spot["id"])
            logger.debug(f"Спот {spot['name']}: active_count={active_count}, arriving_users={len(arriving_users)}")
            if active_count > 0 or len(arriving_users) > 0:
                distance = haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])
                active_spots.append((spot, distance))
        logger.info(f"Найдено активных спотов для user_id={user_id}: {len(active_spots)}")
        if not active_spots:
            logger.info(f"Активные споты не найдены для user_id={user_id}")
            await message.answer(
                "🌬️🚫🔍 На спотах активность не обнаружена!\n"
                "🚗📍🤔 Собрался или приехал на спот и решил остаться?\n"
                "📢📍🤙 Дай знать — отметь себя на споте!\n"
                "🌍👥🌪️🪁 Все будут знать, где сегодня вкатывают.",
                reply_markup=ReplyKeyboardRemove()
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
            await message.answer("Вернитесь в меню:", reply_markup=keyboard)
            await state.clear()
            return
        nearest_spots = sorted(active_spots, key=lambda x: x[1])[:5]
        response_title = "🔍 **Активные споты:**\n\n"
    else:
        # Логика для nearby_spots
        distances = [(spot, haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])) for spot in spots]
        nearest_spots = sorted(distances, key=lambda x: x[1])[:5]
        response_title = "🌤️ **Ближайшие споты:**\n\n"
        logger.info(f"Найдено ближайших спотов для user_id={user_id}: {len(nearest_spots)}")

    # Собираем координаты всех спотов для параллельных запросов погоды
    weather_tasks = [get_windy_forecast(spot["lat"], spot["lon"]) for spot, _ in nearest_spots]
    weather_results = await asyncio.gather(*weather_tasks, return_exceptions=True)
    weather_data = []
    for result in weather_results:
        if isinstance(result, Exception):
            logger.error(f"Ошибка при запросе погоды: {result}")
            weather_data.append(None)
        else:
            weather_data.append(result)

    # Формируем ответ
    response = response_title
    for (spot, distance), wind_data in zip(nearest_spots, weather_data):
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

        # Формируем информацию о погоде
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

    # Формируем клавиатуру
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"plan_to_arrive_{spot['id']}")]
            for spot, distance in nearest_spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )

    logger.info(f"Отправка ответа для user_id={user_id}, callback_data={callback_data}")
    await message.answer(response, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.clear()

@spots_router.callback_query(F.data.startswith("plan_to_arrive_"))
async def plan_to_arrive(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для планирования приезда на спот."""
    user_id = callback.from_user.id
    spot_id = int(callback.data.split("_")[-1])
    logger.info(f"Планирование приезда для user_id={user_id}, spot_id={spot_id}")
    spot = await get_spot_by_id(spot_id)
    if not spot:
        logger.warning(f"Спот не найден: spot_id={spot_id}")
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return

    await state.update_data(spot_id=spot_id)
    await callback.message.edit_text(f"Вы выбрали спот: {spot['name']}\nКогда вы планируете приехать?")
    keyboard = create_arrival_time_keyboard()
    await callback.message.answer("Выберите время прибытия:", reply_markup=keyboard)
    await state.set_state(NearbySpotsState.setting_arrival_time)
    await callback.answer()

@spots_router.callback_query(F.data.startswith("arrival_"), NearbySpotsState.setting_arrival_time)
async def process_arrival_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обработчик выбора времени прибытия."""
    user_id = callback.from_user.id
    arrival_str = callback.data.split("_")[1]
    now = datetime.utcnow().replace(tzinfo=pytz.utc)

    if arrival_str in ["1", "2", "3"]:
        arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()
    else:
        logger.warning(f"Некорректное время прибытия для user_id={user_id}: {arrival_str}")
        await callback.answer("❌ Некорректный формат времени.")
        return

    data = await state.get_data()
    spot_id = data["spot_id"]
    logger.info(f"Создание чек-ина для user_id={user_id}, spot_id={spot_id}, arrival_time={arrival_time}")
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

@spots_router.callback_query(F.data == "cancel_checkin", NearbySpotsState.setting_arrival_time)
async def cancel_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отмены планирования приезда."""
    user_id = callback.from_user.id
    logger.info(f"Отмена чек-ина для user_id={user_id}")
    await callback.message.edit_text("❌ Планирование приезда отменено.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@spots_router.callback_query(F.data == "confirm_arrival")
async def confirm_arrival(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик подтверждения прибытия на спот."""
    user_id = callback.from_user.id
    data = await state.get_data()
    spot_id = data.get("spot_id")
    logger.info(f"Подтверждение прибытия для user_id={user_id}, spot_id={spot_id}")
    if not spot_id:
        logger.warning(f"Спот не выбран для user_id={user_id}")
        await callback.message.answer("❌ Спот не выбран. Пожалуйста, начните сначала.")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await callback.answer()
        return

    spot = await get_spot_by_id(spot_id)
    if not spot:
        logger.warning(f"Спот не найден: spot_id={spot_id}")
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return

    await checkin_user(user_id, spot_id, checkin_type=1)
    await callback.message.edit_text(f"✅ Вы подтвердили прибытие на спот '{spot['name']}'! 🏄‍♂️")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()