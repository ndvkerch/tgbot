import logging
import math
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder  # Добавляем для определения часового пояса
import pytz

from aiogram import Router, types, F, Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_active_checkin, get_checkins_for_spot, checkin_user, get_user, add_or_update_user
from services.weather import get_windy_forecast, wind_direction_to_text

logging.basicConfig(level=logging.INFO)
spots_router = Router()

# Определение состояний FSM
class NearbySpotsState(StatesGroup):
    waiting_for_location = State()
    setting_arrival_time = State()

# Вспомогательная функция для вычисления расстояния
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками на Земле (в километрах) с помощью формулы гаверсинуса."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# Функция для создания клавиатуры выбора времени прибытия
def create_arrival_time_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора времени прибытия."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 1 час", callback_data="arrival_1"),
         InlineKeyboardButton(text="Через 2 часа", callback_data="arrival_2"),
         InlineKeyboardButton(text="Через 3 часа", callback_data="arrival_3")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])

# Инициализация TimezoneFinder
tf = TimezoneFinder()

# Запрос геолокации для поиска ближайших спотов
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

# Обработка геолокации и отображение ближайших спотов
@spots_router.message(NearbySpotsState.waiting_for_location, F.location)
async def process_location_for_nearby_spots(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию, определяем часовой пояс и показываем ближайшие споты."""
    user_id = message.from_user.id
    user_lat = message.location.latitude
    user_lon = message.location.longitude

    # Определяем часовой пояс по координатам
    timezone_name = tf.timezone_at(lat=user_lat, lng=user_lon)
    if not timezone_name:
        timezone_name = "UTC"  # Fallback на UTC, если часовой пояс не найден
    user_timezone = pytz.timezone(timezone_name)

    # Обновляем часовой пояс пользователя в базе данных
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]])
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Вычисляем расстояния до всех спотов
    distances = [(spot, haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])) for spot in spots]
    nearest_spots = sorted(distances, key=lambda x: x[1])[:5]

    # Формируем ответ
    response = "🔍 **Ближайшие споты:**\n\n"
    for spot, distance in nearest_spots:
        on_spot_count, on_spot_users, arriving_users = await get_checkins_for_spot(spot["id"])
        on_spot_names = ", ".join(user["first_name"] for user in on_spot_users) if on_spot_users else "никого"

        # Преобразуем время прибытия в часовой пояс пользователя
        arriving_info = "нет"
        if arriving_users:
            arriving_info_list = []
            for user in arriving_users:
                arrival_time_str = user["arrival_time"]
                if "T" not in arrival_time_str:  # Для старых записей без даты
                    arrival_time_str = f"{datetime.utcnow().date()}T{arrival_time_str}+00:00"
                utc_time = datetime.fromisoformat(arrival_time_str.replace("Z", "+00:00"))
                local_time = utc_time.replace(tzinfo=pytz.utc).astimezone(user_timezone)
                arriving_info_list.append(f"{user['first_name']} ({local_time.strftime('%H:%M')})")
            arriving_info = ", ".join(arriving_info_list)

        # Данные о ветре
        wind_data = await get_windy_forecast(spot["lat"], spot["lon"])
        wind_info = "🌬 *Ветер:* Данные недоступны."
        if wind_data:
            wind_speed = wind_data["speed"]
            wind_direction = wind_data["direction"]
            direction_text = wind_direction_to_text(wind_direction)
            wind_info = f"🌬 *Ветер:* {wind_speed:.1f} м/с, {direction_text} ({wind_direction:.0f}°)"

        response += (
            f"🏄‍♂️ **{spot['name']}**\n"
            f"📍 *Расстояние:* {distance:.2f} км\n"
            f"{wind_info}\n"
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

# Обработка неверного ввода вместо геолокации
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

# Обработка нажатия на кнопку "Собираюсь на спот"
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

# Обработка выбора времени прибытия
@spots_router.callback_query(F.data.startswith("arrival_"), NearbySpotsState.setting_arrival_time)
async def process_arrival_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем время прибытия и регистрируем чек-ин."""
    arrival_str = callback.data.split("_")[1]
    now = datetime.utcnow().replace(tzinfo=pytz.utc)  # Добавляем часовой пояс

    if arrival_str in ["1", "2", "3"]:
        arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()
    else:
        # Обработка формата "HH:MM"
        try:
            target_hour, target_minute = map(int, arrival_str.split(":"))
        except ValueError:
            await callback.answer("❌ Некорректный формат времени. Используйте ЧЧ:ММ (например, 21:47).")
            return

        # Создаем datetime с текущей датой и указанным временем
        target_time = datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=target_hour,
            minute=target_minute,
            tzinfo=pytz.utc  # Явно указываем часовой пояс
        ).replace(tzinfo=pytz.utc)
        
        # Если время уже прошло сегодня, переносим на завтра
        if target_time < now:
            target_time += timedelta(days=1)
        
        arrival_time = target_time.isoformat()

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    await checkin_user(user_id, spot_id, checkin_type=2, bot=bot, arrival_time=arrival_time)
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

# Обработка отмены планирования
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