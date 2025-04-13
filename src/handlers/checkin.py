import logging
import aiosqlite
import pytz
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from aiogram import Bot, Router, types, F
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import DB_PATH, get_spots, add_spot, checkin_user, get_active_checkin, get_spot_by_id, update_checkin_to_arrived, update_spot_name, update_spot_location, delete_spot, checkout_user, get_user, add_or_update_user, notify_favorite_users
from keyboards import get_main_keyboard, create_location_request_keyboard, create_spot_keyboard, create_checkin_type_keyboard, create_duration_keyboard, create_arrival_time_keyboard, create_arrival_confirmation_keyboard, create_confirm_delete_keyboard, create_checkin_new_spot_keyboard, create_uncheckin_keyboard, create_back_to_menu_keyboard
from utils.geo import get_cached_location, set_cached_location, GeoState, haversine_distance

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
checkin_router = Router()

# Определение состояний для FSM
class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()
    confirming_location = State()  # Новое состояние для подтверждения геолокации
    naming_spot = State()
    editing_location = State()
    editing_name = State()
    confirming_delete = State()
    selecting_checkin_type = State()
    setting_duration = State()
    setting_arrival_time = State()
    confirming_arrival = State()

# Блок 1: Вспомогательные функции
async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    user = await get_user(user_id)
    if user:
        result = user["is_admin"]
        logger.info(f"Проверка: пользователь {user_id} является админом? {result}")
        return result
    return False

async def get_nearest_spots(user_lat: float, user_lon: float, spots: List[dict], limit: int = 10) -> List[dict]:
    """Возвращает ближайшие споты, отсортированные по расстоянию."""
    distances = [
        {**spot, "distance": haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"])}
        for spot in spots
    ]
    nearest = sorted(distances, key=lambda x: x["distance"])[:limit]
    logger.info(f"Найдено {len(nearest)} ближайших спотов для lat={user_lat}, lon={user_lon}")
    return nearest

# Блок 2: Обработчики для процесса чек-ина
@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор спота для чек-ина с использованием геолокации."""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if not user:
        await add_or_update_user(
            user_id=user_id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            username=callback.from_user.username
        )
    
    logger.info(f"Пользователь {user_id} нажал на Чек-ин")
    
    location = await get_cached_location(user_id)
    if location:
        logger.info(f"Используется кэшированная геолокация для чек-ина user_id={user_id}: {location}")
    else:
        logger.info(f"Кэш геолокации отсутствует для user_id={user_id}, запрашиваем новую")
        await callback.message.answer(
            "❌ Пожалуйста, отправьте геолокацию для поиска ближайших спотов.",
            reply_markup=create_location_request_keyboard()
        )
        await state.set_state(GeoState.waiting_for_spots_location)
        await callback.answer()
        return
    
    user_lat, user_lon = location
    spots = await get_spots() or []
    logger.info(f"Получено {len(spots)} спотов из базы для user_id={user_id}")
    
    if not spots:
        await callback.message.answer(
            "\U0001F50D Похоже, рядом нет спотов.\nОтправьте геолокацию, чтобы создать новый."
        )
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
        await callback.answer()
        return
    
    nearest_spots = await get_nearest_spots(user_lat, user_lon, spots)
    keyboard = create_spot_keyboard(nearest_spots, await is_admin(user_id))
    await callback.message.answer("Выберите спот:", reply_markup=keyboard)
    await state.set_state(CheckinState.choosing_spot)
    await callback.answer()

@checkin_router.message(GeoState.waiting_for_spots_location, F.location)
async def process_location_for_checkin(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию для чек-ина."""
    user_id = message.from_user.id
    lat, lon = message.location.latitude, message.location.longitude
    location = (lat, lon)
    
    await set_cached_location(user_id, location)
    logger.info(f"Геолокация сохранена для чек-ина user_id={user_id}: {location}")
    
    spots = await get_spots() or []
    logger.info(f"Получено {len(spots)} спотов из базы для user_id={user_id}")
    
    if not spots:
        await message.answer(
            "\U0001F50D Похоже, рядом нет спотов.\nОтправьте геолокацию, чтобы создать новый."
        )
        keyboard = create_location_request_keyboard()
        await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
        return
    
    nearest_spots = await get_nearest_spots(lat, lon, spots)
    keyboard = create_spot_keyboard(nearest_spots, await is_admin(user_id))
    await message.answer("Выберите спот:", reply_markup=keyboard)
    await state.set_state(CheckinState.choosing_spot)
    await state.clear()

@checkin_router.callback_query(F.data.startswith("spot_"))
async def select_checkin_type(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал спот, показываем карту и запрашиваем тип действия."""
    spot_id = int(callback.data.split("_")[1])
    spot = await get_spot_by_id(spot_id)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return
    await state.update_data(spot_id=spot_id)
    await state.set_state(CheckinState.selecting_checkin_type)

    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    keyboard = create_checkin_type_keyboard(spot_id)
    await callback.message.answer(f"Вы выбрали спот: {spot['name']}\nВыберите действие:", reply_markup=keyboard)
    await callback.answer()

@checkin_router.callback_query(F.data == "checkin_type_1")
async def checkin_type_1(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    spot_id = data.get("spot_id")
    user_id = callback.from_user.id
    
    if not spot_id:
        await callback.message.answer("❌ Спот не выбран. Пожалуйста, начните заново.")
        await state.clear()
        await callback.answer()
        return
    
    try:
        checkin_id = await checkin_user(user_id, spot_id, checkin_type=1, bot=bot)
        if not checkin_id:
            raise ValueError("Checkin ID not returned")
            
        await state.update_data(checkin_id=checkin_id)
        
        keyboard = create_duration_keyboard()
        await callback.message.edit_text("Сколько вы планируете здесь находиться?")
        await callback.message.answer("Выберите длительность:", reply_markup=keyboard)
        logger.info(f"Состояние оставлено: selecting_checkin_type для пользователя {user_id}")

    except Exception as e:
        logger.error(f"Ошибка создания чек-ина: {str(e)}")
        await callback.message.answer("❌ Не удалось создать запись чек-ина. Попробуйте позже.")
    
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("plan_to_arrive_"))
async def plan_to_arrive(callback: types.CallbackQuery, state: FSMContext):
    spot_id = callback.data.split("_")[-1]
    if not spot_id.isdigit():
        await callback.message.answer("❌ Ошибка выбора спота. Попробуйте снова.")
        await callback.answer()
        return
    spot_id = int(spot_id)
    await state.update_data(spot_id=spot_id)
    
    spot = await get_spot_by_id(spot_id)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return
    
    await callback.message.edit_text(f"Вы выбрали спот: {spot['name']}\nКогда вы планируете приехать?")
    keyboard = create_arrival_time_keyboard()
    await callback.message.answer("Выберите время прибытия:", reply_markup=keyboard)
    await state.set_state(CheckinState.setting_arrival_time)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("duration_"), CheckinState.selecting_checkin_type)
async def process_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    logger.info(f"Сработал process_duration для пользователя {callback.from_user.id}, callback.data={callback.data}, состояние: {current_state}")
    data = await state.get_data()
    user_id = callback.from_user.id
    checkin_id = data.get("checkin_id")
    
    if not checkin_id:
        logger.warning("Сессия устарела: отсутствует checkin_id")
        await callback.answer("❌ Сессия устарела. Начните заново.")
        await state.clear()
        return
    
    duration_hours = int(callback.data.split("_")[1])
    
    try:
        now = datetime.now(pytz.utc)
        end_time = (now + timedelta(hours=duration_hours)).isoformat()
        
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                UPDATE checkins 
                SET 
                    active = 1,
                    end_time = ?,
                    duration_hours = ?,
                    timestamp = ?
                WHERE id = ?
            ''', (end_time, duration_hours, now.isoformat(), checkin_id))
            await conn.commit()
            logger.info(f"Чек-ин {checkin_id} активирован для типа 1, active=1")

        spot = await get_spot_by_id(data["spot_id"])
        await notify_favorite_users(
            spot_id=spot["id"],
            checkin_user_id=user_id,
            bot=bot,
            checkin_type=1,
            arrival_time=None
        )

        keyboard = create_uncheckin_keyboard()
        await callback.message.edit_text(
            f"\u2705 Вы отметились на споте '{spot['name']}'! 🌊",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обновления чек-ина {checkin_id}: {str(e)}")
        await callback.answer("❌ Произошла ошибка")

    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("arrival_"))
async def process_arrival_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    arrival_str = callback.data.split("_")[1]
    now = datetime.now(timezone.utc)
    arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    await checkin_user(user_id, spot_id, checkin_type=2, arrival_time=arrival_time, bot=bot)
    spot = await get_spot_by_id(spot_id)
    await callback.message.edit_text(f"\u2705 Вы запланировали приезд на спот '{spot['name']}'! 🌊")
    
    keyboard = create_arrival_confirmation_keyboard()
    await callback.message.answer("Когда приедете, подтвердите прибытие:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "confirm_arrival")
async def confirm_arrival(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    active_checkin = await get_active_checkin(user_id)
    logger.info(f"Пользователь {user_id} нажал 'Я приехал!'. Активный чек-ин: {active_checkin}")

    if not active_checkin or active_checkin["checkin_type"] != 2:
        await callback.message.edit_text("❌ Нет активного планирования приезда.")
        keyboard = create_back_to_menu_keyboard()
        await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        await callback.answer()
        return

    await state.update_data(checkin_id=active_checkin["id"], spot_id=active_checkin["spot_id"])
    keyboard = create_duration_keyboard()
    await callback.message.edit_text("Вы приехали! Сколько вы планируете здесь находиться?")
    await callback.message.answer("Выберите длительность:", reply_markup=keyboard)
    await state.set_state(CheckinState.setting_duration)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("duration_"), CheckinState.setting_duration)
async def process_arrival_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    logger.info(f"Сработал process_arrival_duration для пользователя {callback.from_user.id}, callback.data={callback.data}, состояние: {current_state}")
    duration_hours = int(callback.data.split("_")[1])

    data = await state.get_data()
    checkin_id = data.get("checkin_id")
    spot_id = data.get("spot_id")

    if not checkin_id or not spot_id:
        logger.warning("Сессия устарела: отсутствует checkin_id или spot_id")
        await callback.message.edit_text("❌ Сессия устарела. Начните заново.")
        await state.clear()
        await callback.answer()
        return

    now = datetime.now(pytz.utc)
    end_time = now + timedelta(hours=duration_hours)

    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute('''
                UPDATE checkins 
                SET 
                    checkin_type = 1,
                    timestamp = ?,
                    duration_hours = ?,
                    end_time = ?,
                    arrival_time = NULL,
                    active = 1
                WHERE id = ?
            ''', (now.isoformat(), duration_hours, end_time.isoformat(), checkin_id))
            await conn.commit()
            logger.info(f"Чек-ин {checkin_id} успешно обновлен: checkin_type=1, arrival_time=NULL, active=1")
        except Exception as e:
            logger.error(f"Ошибка при обновлении чек-ина {checkin_id}: {str(e)}")
            await callback.message.edit_text("❌ Ошибка при обновлении чек-ина.")
            await state.clear()
            await callback.answer()
            return

    spot = await get_spot_by_id(spot_id)
    await notify_favorite_users(
        spot_id=spot_id,
        checkin_user_id=callback.from_user.id,
        bot=bot,
        checkin_type=1,
        arrival_time=None
    )

    keyboard = create_uncheckin_keyboard()
    await callback.message.edit_text(
        f"\u2705 Вы прибыли и отметились на споте '{spot['name']}'! 🌊",
        reply_markup=keyboard
    )

    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "cancel_checkin")
async def cancel_checkin(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    checkin_id = data.get("checkin_id")

    if checkin_id:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("""
                SELECT id FROM checkins 
                WHERE 
                    id = ? 
                    AND end_time IS NULL 
                    AND active = 0
            """, (checkin_id,))
            result = await cursor.fetchone()
            
            if result:
                await cursor.execute("DELETE FROM checkins WHERE id = ?", (checkin_id,))
                await conn.commit()
                logger.info(f"Удалена временная запись чек-ина {checkin_id} для пользователя {user_id}")

    spots = await get_spots() or []
    if spots:
        location = await get_cached_location(user_id)
        if not location:
            await callback.message.answer(
                "❌ Пожалуйста, отправьте геолокацию для поиска ближайших спотов.",
                reply_markup=create_location_request_keyboard()
            )
            await state.set_state(GeoState.waiting_for_spots_location)
            await callback.answer()
            return
        user_lat, user_lon = location
        nearest_spots = await get_nearest_spots(user_lat, user_lon, spots)
        keyboard = create_spot_keyboard(nearest_spots, await is_admin(user_id))
        await callback.message.edit_text("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text(
            "\U0001F50D Похоже, рядом нет спотов.\nОтправьте геолокацию, чтобы создать новый."
        )
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)

    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("late_arrival_confirm_"))
async def handle_late_arrival(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    checkin_id = int(callback.data.split("_")[3])
    logger.info(f"Обработка late_arrival_confirm для пользователя {user_id}, checkin_id={checkin_id}")
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.cursor()
        await cursor.execute("""
            SELECT id, spot_id 
            FROM checkins 
            WHERE id = ? AND user_id = ? AND checkin_type = 2
        """, (checkin_id, user_id))
        result = await cursor.fetchone()
        
        if not result:
            logger.warning(f"Не найдена запись чек-ина с id={checkin_id} для пользователя {user_id}")
            await callback.message.edit_text("❌ Не удалось найти данные о вашем прибытии.")
            await state.clear()
            await callback.answer()
            return
        
        checkin_id, spot_id = result
    
    await state.update_data(checkin_id=checkin_id, spot_id=spot_id)
    keyboard = create_duration_keyboard()
    await callback.message.edit_text(
        "Вы подтвердили прибытие. Выберите продолжительность пребывания:",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.setting_duration)
    await callback.answer()

# Блок 3: Обработчики для редактирования и удаления спотов
@checkin_router.callback_query(F.data.startswith("edit_spot_"))
async def edit_spot(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await is_admin(user_id):
        await callback.answer("❌ У вас нет прав для редактирования спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    spots = await get_spots()
    spot = next((s for s in spots if s["id"] == spot_id), None)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await state.clear()
        return

    await state.update_data(spot_id=spot_id)
    await callback.message.answer(f"Текущая геолокация спота '{spot['name']}':")
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    
    keyboard = create_location_request_keyboard()
    await callback.message.answer("\u2705 Отправьте новую геолокацию для спота:", reply_markup=keyboard)
    await state.set_state(CheckinState.editing_location)
    await callback.answer()

@checkin_router.message(CheckinState.editing_location, F.location)
async def process_new_location(message: types.Message, state: FSMContext):
    new_lat, new_lon = message.location.latitude, message.location.longitude
    data = await state.get_data()
    spot_id = data["spot_id"]
    await update_spot_location(spot_id, new_lat, new_lon)
    logger.info(f"Админ {message.from_user.id} обновил геопозицию спота ID {spot_id}: Lat={new_lat}, Lon={new_lon}")

    await message.answer("📍 Геопозиция обновлена! Теперь введите новое название спота:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CheckinState.editing_name)

@checkin_router.message(CheckinState.editing_location)
async def handle_invalid_new_location(message: types.Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить новую геолокацию'.")
    keyboard = create_location_request_keyboard()
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@checkin_router.message(CheckinState.editing_name, F.text)
async def process_new_spot_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    spot_id = data["spot_id"]
    await update_spot_name(spot_id, new_name)
    logger.info(f"Админ {message.from_user.id} обновил название спота ID {spot_id} на '{new_name}'")

    keyboard = create_back_to_menu_keyboard()
    await message.answer(f"\u2705 Название спота обновлено на '{new_name}'!", reply_markup=keyboard)
    await state.clear()

@checkin_router.message(CheckinState.editing_name)
async def handle_invalid_new_spot_name(message: types.Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, введите новое название спота текстом.")

@checkin_router.callback_query(F.data.startswith("delete_spot_"))
async def confirm_delete_spot(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await is_admin(user_id):
        await callback.answer("❌ У вас нет прав для удаления спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    await state.update_data(spot_id=spot_id)
    
    keyboard = create_confirm_delete_keyboard(spot_id)
    await callback.message.edit_text("Вы уверены, что хотите удалить этот спот?", reply_markup=keyboard)
    await state.set_state(CheckinState.confirming_delete)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_spot_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await is_admin(user_id):
        await callback.answer("❌ У вас нет прав для удаления спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    await delete_spot(spot_id)
    logger.info(f"Админ {user_id} удалил спот ID {spot_id}")

    keyboard = create_back_to_menu_keyboard()
    await callback.message.edit_text("\u2705 Спот удалён!", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "cancel_delete")
async def cancel_delete_spot(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    spots = await get_spots() or []
    if spots:
        location = await get_cached_location(user_id)
        if not location:
            await callback.message.answer(
                "❌ Пожалуйста, отправьте геолокацию для поиска ближайших спотов.",
                reply_markup=create_location_request_keyboard()
            )
            await state.set_state(GeoState.waiting_for_spots_location)
            await callback.answer()
            return
        user_lat, user_lon = location
        nearest_spots = await get_nearest_spots(user_lat, user_lon, spots)
        keyboard = create_spot_keyboard(nearest_spots, await is_admin(user_id))
        await callback.message.edit_text("Выберите спот для чек-ина:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text(
            "\U0001F50D Похоже, рядом нет спотов.\nОтправьте геолокацию, чтобы создать новый."
        )
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("cancel_late_arrival_"))
async def cancel_late_arrival(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    checkin_id = int(callback.data.split("_")[3])
    logger.info(f"Обработка cancel朝鮮_late_arrival для пользователя {user_id}, checkin_id={checkin_id}")
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.cursor()
        await cursor.execute("""
            SELECT id 
            FROM checkins 
            WHERE id = ? AND user_id = ? AND checkin_type = 2
        """, (checkin_id, user_id))
        result = await cursor.fetchone()
        
        if result:
            await cursor.execute("DELETE FROM checkins WHERE id = ?", (checkin_id,))
            await conn.commit()
            logger.info(f"Чек-ин {checkin_id} удалён для пользователя {user_id}")
        else:
            logger.warning(f"Не найдена запись чек-ина с id={checkin_id} для пользователя {user_id}")
    
    await callback.message.edit_text("❌ Вы отменили прибытие на спот.")
    keyboard = create_back_to_menu_keyboard()
    await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

# Блок 4: Обработчики для добавления нового спота
@checkin_router.callback_query(F.data == "add_spot")
async def request_location(callback: types.CallbackQuery, state: FSMContext):
    """Просим отправить геолокацию для создания спота."""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал добавить новый спот")
    current_state = await state.get_state()
    logger.debug(f"Текущее состояние перед установкой adding_spot: {current_state}")
    await callback.message.delete()
    await callback.message.answer(
        "\u2705 Отправьте геолокацию нового спота.",
        reply_markup=create_location_request_keyboard()
    )
    await state.set_state(CheckinState.adding_spot)
    new_state = await state.get_state()
    logger.debug(f"Состояние после установки: {new_state}")
    await callback.answer()

@checkin_router.message(CheckinState.adding_spot, F.location)
async def process_location(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию и запрашиваем подтверждение."""
    user_id = message.from_user.id
    lat, lon = message.location.latitude, message.location.longitude
    logger.info(f"Пользователь {user_id} отправил геолокацию для нового спота: {lat}, {lon}")
    
    await state.update_data(lat=lat, lon=lon)
    # Показываем venue вместо обычной карты
    await message.answer("📍 Вы выбрали эту геолокацию:")
    await message.answer_venue(
        latitude=lat,
        longitude=lon,
        title="Новый спот",
        address="Спот для кайтсерфинга"
    )
    # Используем клавиатуру из keyboards.py
    keyboard = create_confirm_location_keyboard()
    await message.answer("Подтвердите геолокацию:", reply_markup=keyboard)
    await state.set_state(CheckinState.confirming_location)

@checkin_router.callback_query(CheckinState.confirming_location, F.data == "confirm_location")
async def confirm_location(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатываем подтверждение геолокации."""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} подтвердил геолокацию")
    await callback.message.edit_text("📍 Геолокация подтверждена!")
    await callback.message.answer("Введите название спота:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CheckinState.naming_spot)
    await callback.answer()

@checkin_router.callback_query(CheckinState.confirming_location, F.data == "change_location")
async def change_location(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем другую геолокацию."""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал указать другую геолокацию")
    await callback.message.edit_text("\u2705 Отправьте новую геолокацию для спота:")
    await callback.message.answer("Нажмите кнопку ниже:", reply_markup=create_location_request_keyboard())
    await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.message(CheckinState.adding_spot)
async def handle_invalid_location(message: types.Message, state: FSMContext):
    """Обрабатываем некорректный ввод вместо геолокации."""
    logger.warning(f"Пользователь {message.from_user.id} отправил некорректные данные вместо геолокации: {message.content_type}")
    await message.answer(
        "❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'."
    )
    await message.answer("Нажмите кнопку ниже:", reply_markup=create_location_request_keyboard())

@checkin_router.message(CheckinState.naming_spot, F.text)
async def add_new_spot_handler(message: types.Message, state: FSMContext, bot: Bot):
    """Обрабатываем название спота и добавляем его в базу."""
    spot_name = message.text.strip()
    if not spot_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    lat, lon = data["lat"], data["lon"]
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} создаёт спот '{spot_name}' с координатами: {lat}, {lon}")

    spot_id = await add_spot(spot_name, lat, lon, creator_id=user_id)
    await state.update_data(spot_id=spot_id)
    
    keyboard = create_checkin_new_spot_keyboard()
    await message.answer(
        f"\u2705 Спот '{spot_name}' успешно создан!\nХотите отметить свое присутствие?",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.choosing_spot)
    await state.update_data(new_spot_created=True)

@checkin_router.callback_query(F.data == "checkin_new_spot")
async def handle_new_spot_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатываем чек-ин на новом споте."""
    data = await state.get_data()
    spot_id = data.get("spot_id")
    
    if not spot_id:
        await callback.answer("❌ Ошибка: спот не найден")
        return
        
    spot = await get_spot_by_id(spot_id)
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    keyboard = create_checkin_type_keyboard(spot_id)
    await callback.message.answer(
        f"Вы создали спот: {spot['name']}\nВыберите действие:",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.selecting_checkin_type)
    await callback.answer()

@checkin_router.message(CheckinState.naming_spot)
async def handle_invalid_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем некорректный ввод вместо названия спота."""
    await message.answer("❌ Пожалуйста, введите название спота текстом.")

# Блок 5: Обработчики для навигации и разчекина
@checkin_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.delete()
    reply_markup = await get_main_keyboard(user_id)
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=reply_markup)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "uncheckin")
async def process_uncheckin(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    active_checkin = await get_active_checkin(user_id)
    
    if not active_checkin:
        await callback.message.edit_text("❌ Вы еще не отметились на споте.")
        keyboard = create_back_to_menu_keyboard()
        await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await callback.answer()
        return

    await checkout_user(active_checkin["id"])
    spot = await get_spot_by_id(active_checkin["spot_id"])
    await callback.message.edit_text(f"\u2705 Вы покинули спот '{spot['name']}'! 🚪")
    
    keyboard = create_back_to_menu_keyboard()
    reply_markup = await get_main_keyboard(user_id)
    await callback.message.answer("Вернитесь в меню:", reply_markup=reply_markup)
    await state.clear()
    await callback.answer()