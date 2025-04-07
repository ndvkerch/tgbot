import logging
import math
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder
import pytz

from aiogram import Router, types, F, Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_active_checkin, get_checkins_for_spot, checkin_user, get_user, add_or_update_user
from services.weather import get_open_meteo_forecast as get_windy_forecast, wind_direction_to_text

logging.basicConfig(level=logging.INFO)
spots_router = Router()

class NearbySpotsState(StatesGroup):
    waiting_for_location = State()
    setting_arrival_time = State()

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками на Земле (в километрах) с помощью формулы гаверсинуса."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def create_arrival_time_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора времени прибытия."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 1 час", callback_data="arrival_1"),
         InlineKeyboardButton(text="Через 2 часа", callback_data="arrival_2"),
         InlineKeyboardButton(text="Через 3 часа", callback_data="arrival_3")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])

tf = TimezoneFinder()

@spots_router.callback_query(F.data == "nearby_spots")
async def request_location_for_nearby_spots(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем геолокацию для поиска ближайших спотов."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
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

    # Определяем часовой пояс
    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon) or "UTC"
    user_timezone = pytz.timezone(timezone_name)

    # Обновляем данные пользователя
    user = await get_user(user_id)
    await add_or_update_user(
        user_id=user_id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
        timezone=timezone_name
    )

    # Получаем все споты
    spots = await get_spots() or []
    if not spots:
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Фильтруем споты с активными чек-инами
    active_spots = []
    for spot in spots:
        active_count, active_users, arriving_users = await get_checkins_for_spot(spot["id"])  # Распаковка трёх значений
        if active_count > 0 or len(arriving_users) > 0:  # Исправлено условие
            distance = haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])
            active_spots.append((spot, distance))

    # Сортируем по расстоянию и берём до 5 ближайших
    nearest_active_spots = sorted(active_spots, key=lambda x: x[1])[:5]

    if not nearest_active_spots:
        # Если нет активных спотов, показываем сообщение с шуткой
        await message.answer(
            "🌬️🚫🔍 На спотах активность не обнаружена! 🚗📍🤔 Приехал на спот и решил остаться? 📢📍🤙 Дай знать — отметь себя на споте! 🌍👥🌪️🪁 Все будут знать, где сегодня вкатывают.",
            reply_markup=ReplyKeyboardRemove()
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
        )
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Формируем ответ
    response = "🔍 **Активные споты:**\n\n"
    for spot, distance in nearest_active_spots:
        active_count, active_users, arriving_users = await get_checkins_for_spot(spot["id"])  # Распаковка трёх значений
        on_spot_names = ", ".join(user["first_name"] for user in active_users) if active_users else "никого"

        arriving_info = "нет"
        if arriving_users:
            arriving_info_list = []
            for user in arriving_users:
                arrival_time_str = user["arrival_time"]
                if "T" not in arrival_time_str:  # Для старых записей
                    arrival_time_str = f"{datetime.utcnow().date()}T{arrival_time_str}+00:00"
                utc_time = datetime.fromisoformat(arrival_time_str.replace("Z", "+00:00"))
                local_time = utc_time.replace(tzinfo=pytz.utc).astimezone(user_timezone)
                arriving_info_list.append(f"{user['first_name']} ({local_time.strftime('%H:%M')})")
            arriving_info = ", ".join(arriving_info_list)

        # Получаем данные о ветре и температуре
        wind_data = await get_windy_forecast(spot["lat"], spot["lon"])
        wind_info = "🌬 *Ветер:* Данные недоступны."
        temp_info = "🌡 *Температура:* Данные недоступны."
        if wind_data:
            wind_speed = wind_data["speed"]
            wind_direction = wind_data["direction"]
            direction_text = wind_direction_to_text(wind_direction)
            wind_info = f"🌬 *Ветер:* {wind_speed:.1f} м/с, {direction_text} ({wind_direction:.0f}°)"
            # Добавляем температуру, если она доступна
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

    # Клавиатура
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"plan_to_arrive_{spot['id']}")]
            for spot, distance in nearest_active_spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )

    await message.answer(response, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.clear()

@spots_router.message(NearbySpotsState.waiting_for_location)
async def handle_invalid_location_for_nearby_spots(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не геолокацию."""
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@spots_router.callback_query(F.data.startswith("plan_to_arrive_"))
async def plan_to_arrive(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем время прибытия после выбора спота."""
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
    await state.set_state(NearbySpotsState.setting_arrival_time)
    await callback.answer()

@spots_router.callback_query(F.data.startswith("arrival_"), NearbySpotsState.setting_arrival_time)
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

    # Удаляем параметр bot=bot из вызова функции checkin_user
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
    """Отмена планирования приезда."""
    await callback.message.edit_text("❌ Планирование приезда отменено.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()