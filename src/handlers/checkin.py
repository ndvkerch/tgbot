import logging
import aiosqlite
import pytz
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router, types, F
from aiogram.types import ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import (
    DB_PATH,
    get_spots,
    add_spot,
    checkin_user,
    get_active_checkin,
    get_spot_by_id,
    update_checkin_to_arrived,
    update_spot_name,
    update_spot_location,
    delete_spot,
    checkout_user,
    get_user,
    add_or_update_user,
    deactivate_all_checkins,
    notify_favorite_users,
)
from keyboards import (
    get_main_keyboard,
    create_spot_keyboard,
    create_checkin_type_keyboard,
    create_duration_keyboard,
    create_arrival_time_keyboard,
    create_arrival_confirmation_keyboard,
    create_location_request_keyboard,
    create_back_to_menu_keyboard,
    create_confirm_delete_keyboard,
    create_checkin_new_spot_keyboard,
    create_uncheckin_keyboard,
    create_confirm_arrival_keyboard,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
checkin_router = Router()

# Определение состояний для FSM
class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()
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
        logging.info(f"Проверка: пользователь {user_id} является админом? {result}")
        return result
    return False

# Блок 2: Обработчики для процесса чек-ина
@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующего спота или добавление нового."""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if not user:
        await add_or_update_user(
            user_id=user_id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            username=callback.from_user.username
        )
    
    logging.info(f"Пользователь {user_id} нажал на Чек-ин (callback)")
    spots = await get_spots() or []

    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))
        await callback.message.answer("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.answer("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

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
    keyboard = create_checkin_type_keyboard(spot_id)  # Передаем spot_id
    await callback.message.answer(f"Вы выбрали спот: {spot['name']}\nВыберите действие:", reply_markup=keyboard)
    await callback.answer()

@checkin_router.callback_query(F.data == "checkin_type_1")
async def checkin_type_1(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    spot_id = data.get("spot_id")
    user_id = callback.from_user.id
    
    if not spot_id:
        await callback.message.answer("❌ Спот не выбран. Пожалуйста, начните процесс заново.")
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

@checkin_router.callback_query(F.data == "checkin_type_2")
async def checkin_type_2(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spot_id = data.get("spot_id")
    if not spot_id:
        await callback.message.answer("❌ Спот не выбран. Пожалуйста, начните процесс заново.")
        await state.clear()
        await callback.answer()
        return
    # Вызываем plan_to_arrive с нужным callback_data
    callback.data = f"plan_to_arrive_{spot_id}"
    await plan_to_arrive(callback, state)

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
        if bot:
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
    
    keyboard = create_confirm_arrival_keyboard()
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
    await state.set_state(CheckinState.setting_duration)
    logger.info(f"Установлено состояние CheckinState.setting_duration для пользователя {user_id}, данные: {await state.get_data()}")

    keyboard = create_duration_keyboard()
    await callback.message.edit_text("Вы приехали! Сколько вы планируете здесь находиться?")
    await callback.message.answer("Выберите длительность:", reply_markup=keyboard)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("duration_"), CheckinState.setting_duration)
async def process_arrival_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    logger.info(f"Сработал process_arrival_duration для пользователя {callback.from_user.id}, callback.data={callback.data}, состояние: {current_state}")
    duration_hours = int(callback.data.split("_")[1])

    data = await state.get_data()
    checkin_id = data.get("checkin_id")
    spot_id = data.get("spot_id")
    logger.info(f"Данные из состояния: {data}")

    if not checkin_id or not spot_id:
        logger.warning("Сессия устарела: отсутствует checkin_id или spot_id")
        await callback.message.edit_text("❌ Сессия устарела. Начните заново.")
        await state.clear()
        await callback.answer()
        return

    now = datetime.now(pytz.utc)
    end_time = now + timedelta(hours=duration_hours)
    logger.info(f"Параметры обновления чек-ина {checkin_id}: timestamp={now.isoformat()}, end_time={end_time.isoformat()}")

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
    logger.info(f"Состояние очищено после успешного чек-ина {checkin_id}")
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
                logger.info(f"Удалена временная запись чекина {checkin_id} для пользователя {user_id}")

    spots = await get_spots() or []
    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))
        await callback.message.edit_text("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)

    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("plan_to_arrive_"))
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
    await state.set_state(CheckinState.setting_arrival_time)
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
            await callback.message.edit_text("❌ Не удалось найти данные о вашем прибытии. Возможно, запись устарела.")
            await state.clear()
            await callback.answer()
            return
        
        checkin_id, spot_id = result
        logger.info(f"Найден чек-ин {checkin_id} для пользователя {user_id} на споте {spot_id}")
    
    await state.update_data(checkin_id=checkin_id, spot_id=spot_id)
    logger.info(f"Данные сохранены в состояние: checkin_id={checkin_id}, spot_id={spot_id}")
    
    keyboard = create_duration_keyboard()
    await callback.message.edit_text(
        "Вы подтвердили прибытие. Выберите продолжительность пребывания:",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.setting_duration)
    logger.info(f"Пользователь {user_id} переведён в состояние setting_duration")
    
    await callback.answer()

# Блок 3: Обработчики для редактирования и удаления спотов (для админов)
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
    logging.info(f"Админ {message.from_user.id} обновил геопозицию спота ID {spot_id}: Lat={new_lat}, Lon={new_lon}")

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
    logging.info(f"Админ {message.from_user.id} обновил название спота ID {spot_id} на '{new_name}'")

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
    logging.info(f"Админ {user_id} удалил спот ID {spot_id}")

    keyboard = create_back_to_menu_keyboard()
    await callback.message.edit_text("\u2705 Спот удалён!", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "cancel_delete")
async def cancel_delete_spot(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    spots = await get_spots() or []
    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))
        await callback.message.edit_text("Выберите спот для чекаина:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = create_location_request_keyboard()
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("cancel_late_arrival_"))
async def cancel_late_arrival(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    checkin_id = int(callback.data.split("_")[3])
    logger.info(f"Обработка cancel_late_arrival для пользователя {user_id}, checkin_id={checkin_id}")
    
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
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} выбрал добавить новый спот")
    keyboard = create_location_request_keyboard()
    await callback.message.delete()
    await callback.message.answer("\u2705 Отправьте свою геолокацию, чтобы создать новый спот.", reply_markup=keyboard)
    await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.message(CheckinState.adding_spot, F.location)
async def process_location(message: types.Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} отправил геолокацию: {lat}, {lon}")
    await state.update_data(lat=lat, lon=lon)
    await message.answer("📍 Геолокация получена! Теперь введите название спота:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CheckinState.naming_spot)

@checkin_router.message(CheckinState.adding_spot)
async def handle_invalid_location(message: types.Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.")
    keyboard = create_location_request_keyboard()
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@checkin_router.message(CheckinState.naming_spot, F.text)
async def add_new_spot_handler(message: types.Message, state: FSMContext, bot: Bot):
    spot_name = message.text.strip()
    if not spot_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    lat, lon = data["lat"], data["lon"]
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} создаёт спот '{spot_name}' с координатами: {lat}, {lon}")

    spot_id = await add_spot(spot_name, lat, lon, creator_id=user_id)
    await state.update_data(spot_id=spot_id)
    
    keyboard = create_checkin_new_spot_keyboard()
    await message.answer(
        f"\u2705 Спот '{spot_name}' успешно создан!\n"
        "Хотите отметить свое присутствие на споте?",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.choosing_spot)
    await state.update_data(new_spot_created=True)

@checkin_router.callback_query(F.data == "checkin_new_spot")
async def handle_new_spot_checkin(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spot_id = data.get("spot_id")
    
    if not spot_id:
        await callback.answer("❌ Ошибка: спот не найден")
        return
        
    spot = await get_spot_by_id(spot_id)
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    
    keyboard = create_checkin_type_keyboard()
    await callback.message.answer(
        f"Вы создали спот: {spot['name']}\nВыберите действие:", 
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.selecting_checkin_type)
    await callback.answer()

@checkin_router.message(CheckinState.naming_spot)
async def handle_invalid_spot_name(message: types.Message, state: FSMContext):
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
    
    reply_markup = await get_main_keyboard(user_id)
    await callback.message.answer("Вернитесь в меню:", reply_markup=reply_markup)
    await state.clear()
    await callback.answer()