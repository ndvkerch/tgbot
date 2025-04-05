import logging
from datetime import datetime, timedelta

from aiogram import Bot, Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, add_spot, checkin_user, get_active_checkin, get_spot_by_id, update_checkin_to_arrived, update_spot_name, update_spot_location, delete_spot, checkout_user, get_user, add_or_update_user
from keyboards import get_main_keyboard  # Импортируем динамическую клавиатуру

# Настройка логирования
logging.basicConfig(level=logging.INFO)
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
    user = await get_user(user_id)  # Добавляем await
    if user:
        result = user["is_admin"]
        logging.info(f"Проверка: пользователь {user_id} является админом? {result}")
        return result
    return False

def create_spot_keyboard(spots: list, is_admin: bool) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком спотов, с дополнительными кнопками для админа."""
    keyboard = []
    for spot in spots:
        spot_buttons = [InlineKeyboardButton(text=spot["name"], callback_data=f"spot_{spot['id']}")]
        if is_admin:
            spot_buttons.append(InlineKeyboardButton(text="✏️", callback_data=f"edit_spot_{spot['id']}"))
            spot_buttons.append(InlineKeyboardButton(text="🗑️", callback_data=f"delete_spot_{spot['id']}"))
        keyboard.append(spot_buttons)
    # Добавляем кнопки "Добавить спот" и "Назад в меню"
    keyboard.append([InlineKeyboardButton(text="➕ Добавить новый спот", callback_data="add_spot")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")])  # Новая кнопка
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_duration_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора длительности пребывания."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 час", callback_data="duration_1"),
         InlineKeyboardButton(text="2 часа", callback_data="duration_2"),
         InlineKeyboardButton(text="3 часа", callback_data="duration_3")],
        [InlineKeyboardButton(text="4 часа", callback_data="duration_4"),
         InlineKeyboardButton(text="5 часов", callback_data="duration_5"),
         InlineKeyboardButton(text="6 часов", callback_data="duration_6")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])
    return keyboard

def create_arrival_time_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора времени прибытия."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 1 час", callback_data="arrival_1"),
         InlineKeyboardButton(text="Через 2 часа", callback_data="arrival_2"),
         InlineKeyboardButton(text="Через 3 часа", callback_data="arrival_3")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])
    return keyboard

def create_arrival_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения прибытия"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я на месте", callback_data="late_arrival_confirm")],
        [InlineKeyboardButton(text="🚪 Отмена", callback_data="cancel_late_arrival")]
    ])

# Блок 2: Обработчики для процесса чек-ина
@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующего спота или добавление нового."""
    user_id = callback.from_user.id
    user = await get_user(user_id)  # Добавляем await
    if not user:
        # Регистрируем пользователя
        await add_or_update_user(  # Добавляем await
            user_id=user_id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            username=callback.from_user.username
        )
    
    logging.info(f"Пользователь {user_id} нажал на Чек-ин (callback)")
    spots = await get_spots() or []  # Добавляем await

    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))  # Добавляем await для is_admin
        await callback.message.answer("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.answer("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("spot_"))
async def select_checkin_type(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал спот, показываем карту и запрашиваем тип действия в одном сообщении."""
    spot_id = int(callback.data.split("_")[1])
    spot = await get_spot_by_id(spot_id)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await callback.answer()
        return

    # Отправляем карту спота
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])

    # Отправляем сообщение о выборе спота с клавиатурой
    keyboard = create_checkin_type_keyboard()
    await callback.message.answer(f"Вы выбрали спот: {spot['name']}\nВыберите действие:", reply_markup=keyboard)

    await state.update_data(spot_id=spot_id)
    await state.set_state(CheckinState.selecting_checkin_type)
    await callback.answer()

@checkin_router.callback_query(F.data == "checkin_type_1")
async def checkin_type_1(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал 'Я уже на споте', запрашиваем длительность."""
    await callback.message.edit_text("Сколько вы планируете здесь находиться?")
    keyboard = create_duration_keyboard()
    await callback.message.answer("Выберите длительность:", reply_markup=keyboard)
    await state.set_state(CheckinState.setting_duration)
    await callback.answer()

@checkin_router.callback_query(F.data == "checkin_type_2")
async def checkin_type_2(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал 'Планирую приехать', запрашиваем время прибытия."""
    await callback.message.edit_text("Когда вы планируете приехать?")
    keyboard = create_arrival_time_keyboard()
    await callback.message.answer("Выберите время прибытия:", reply_markup=keyboard)
    await state.set_state(CheckinState.setting_arrival_time)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("duration_"))
async def process_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем длительность пребывания и выполняем чек-ин."""
    duration_str = callback.data.split("_")[1]
    duration_hours = int(duration_str)

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    # Выполняем чек-ин
    await checkin_user(user_id, spot_id, checkin_type=1, bot=bot, duration_hours=duration_hours)
    
    # Получаем информацию о споте для отображения на карте
    spot = await get_spot_by_id(spot_id)
    
    # Добавляем клавиатуру прямо в отредактированное сообщение
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Покинуть спот", callback_data="uncheckin")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(
        f"\u2705 Вы отметились на споте '{spot['name']}'! 🌊",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("arrival_"))
async def process_arrival_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем время прибытия и выполняем чек-ин."""
    arrival_str = callback.data.split("_")[1]
    now = datetime.utcnow()
    
    # Теперь arrival_str может быть только "1", "2" или "3"
    arrival_time = (now + timedelta(hours=int(arrival_str))).isoformat()

    data = await state.get_data()
    spot_id = data["spot_id"]
    user_id = callback.from_user.id

    # Выполняем чек-ин с типом "Планирую приехать"
    await checkin_user(user_id, spot_id, checkin_type=2, bot=bot, arrival_time=arrival_time)
    
    # Получаем информацию о споте для отображения на карте
    spot = await get_spot_by_id(spot_id)
    await callback.message.edit_text(f"\u2705 Вы запланировали приезд на спот '{spot['name']}'! 🌊")
    
    # Клавиатура для подтверждения прибытия
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я приехал!", callback_data="confirm_arrival")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.answer("Когда приедете, подтвердите прибытие:", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "confirm_arrival")
async def confirm_arrival(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь подтверждает, что приехал на спот."""
    user_id = callback.from_user.id
    active_checkin = await get_active_checkin(user_id)
    if not active_checkin or active_checkin["checkin_type"] != 2:
        await callback.message.edit_text("❌ У вас нет запланированного чек-ина.")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
            ]
        )
        await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        await callback.answer()
        return

    # Сохраняем checkin_id и spot_id в состоянии
    await state.update_data(checkin_id=active_checkin["id"], spot_id=active_checkin["spot_id"])
    await callback.message.edit_text("Сколько вы планируете здесь находиться?")
    keyboard = create_duration_keyboard()
    await callback.message.answer("Выберите длительность:", reply_markup=keyboard)
    await state.set_state(CheckinState.confirming_arrival)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("duration_"), CheckinState.confirming_arrival)
async def process_arrival_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем длительность после подтверждения прибытия."""
    duration_str = callback.data.split("_")[1]
    duration_hours = float(duration_str) if duration_str in ["1", "2", "3"] else None
    
    if duration_str.startswith("until_"):
        target_hour = int(duration_str.split("_")[1].split(":")[0])
        now = datetime.utcnow()
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target_time < now:
            target_time += timedelta(days=1)
        duration_hours = (target_time - now).total_seconds() / 3600

    data = await state.get_data()
    checkin_id = data["checkin_id"]
    spot_id = data.get("spot_id")
    
    # Обновляем чек-ин: переводим в тип 1 и задаём длительность
    await update_checkin_to_arrived(checkin_id, duration_hours)
    
    # Получаем информацию о споте для отображения на карте
    active_checkin = await get_active_checkin(callback.from_user.id)
    spot = await get_spot_by_id(spot_id or active_checkin["spot_id"])
    
    # Добавляем клавиатуру прямо в отредактированное сообщение
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Разчекиниться", callback_data="uncheckin")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(
        f"\u2705 Вы прибыли и отметились на споте '{spot['name']}'! 🌊",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "cancel_checkin")
async def cancel_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Отмена чек-ина, возвращение к выбору спота."""
    spots = await get_spots() or []  # Добавляем await
    user_id = callback.from_user.id
    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))  # Добавляем await для is_admin
        await callback.message.edit_text("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.callback_query(F.data == "plan_to_arrive")
async def plan_to_arrive(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Собираюсь на спот': запрашиваем время прибытия."""
    data = await state.get_data()
    spot_id = data.get("spot_id")
    
    if not spot_id:
        await callback.message.answer("❌ Спот не выбран. Пожалуйста, выберите спот сначала.")
        spots = await get_spots() or []
        keyboard = create_spot_keyboard(spots, await is_admin(callback.from_user.id))
        await callback.message.answer("Выберите спот:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
        await callback.answer()
        return

    spot = await get_spot_by_id(spot_id)
    await callback.message.edit_text(f"Вы выбрали спот: {spot['name']}\nКогда вы планируете приехать?")
    keyboard = create_arrival_time_keyboard()
    await callback.message.answer("Выберите время прибытия:", reply_markup=keyboard)
    await state.set_state(CheckinState.setting_arrival_time)
    await callback.answer()    

@checkin_router.callback_query(F.data == "late_arrival_confirm")
async def handle_late_arrival(callback: types.CallbackQuery, state: FSMContext):
    """Обработка позднего подтверждения"""
    user_id = callback.from_user.id
    await callback.message.answer("Выберите продолжительность пребывания:", 
                               reply_markup=create_duration_keyboard())
    await state.set_state(CheckinState.setting_duration)

# Блок 3: Обработчики для редактирования и удаления спотов (для админов)
@checkin_router.callback_query(F.data.startswith("edit_spot_"))
async def edit_spot(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования спота (только для админа): сначала геопозиция."""
    user_id = callback.from_user.id
    if not await is_admin(user_id):  # Добавляем await
        await callback.answer("❌ У вас нет прав для редактирования спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    spots = await get_spots()  # Добавляем await
    spot = next((s for s in spots if s["id"] == spot_id), None)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await state.clear()
        return

    await state.update_data(spot_id=spot_id)
    await callback.message.answer(f"Текущая геолокация спота '{spot['name']}':")
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить новую геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer("\u2705 Отправьте новую геолокацию для спота:", reply_markup=keyboard)
    await state.set_state(CheckinState.editing_location)
    await callback.answer()

@checkin_router.message(CheckinState.editing_location, F.location)
async def process_new_location(message: types.Message, state: FSMContext):
    """Обновляем геопозицию спота и переходим к редактированию названия."""
    new_lat, new_lon = message.location.latitude, message.location.longitude
    data = await state.get_data()
    spot_id = data["spot_id"]
    await update_spot_location(spot_id, new_lat, new_lon)  # Добавляем await
    logging.info(f"Админ {message.from_user.id} обновил геопозицию спота ID {spot_id}: Lat={new_lat}, Lon={new_lon}")

    await message.answer("📍 Геопозиция обновлена! Теперь введите новое название спота:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CheckinState.editing_name)

@checkin_router.message(CheckinState.editing_location)
async def handle_invalid_new_location(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если админ отправил не геолокацию."""
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить новую геолокацию'.")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить новую геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@checkin_router.message(CheckinState.editing_name, F.text)
async def process_new_spot_name(message: types.Message, state: FSMContext):
    """Обновляем название спота."""
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    spot_id = data["spot_id"]
    await update_spot_name(spot_id, new_name)  # Добавляем await
    logging.info(f"Админ {message.from_user.id} обновил название спота ID {spot_id} на '{new_name}'")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await message.answer(f"\u2705 Название спота обновлено на '{new_name}'!", reply_markup=keyboard)
    await state.clear()

@checkin_router.message(CheckinState.editing_name)
async def handle_invalid_new_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если админ отправил не текст."""
    await message.answer("❌ Пожалуйста, введите новое название спота текстом.")

@checkin_router.callback_query(F.data.startswith("delete_spot_"))
async def confirm_delete_spot(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем подтверждение удаления спота (только для админа)."""
    user_id = callback.from_user.id
    if not await is_admin(user_id):  # Добавляем await
        await callback.answer("❌ У вас нет прав для удаления спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    await state.update_data(spot_id=spot_id)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{spot_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
        ]
    )
    await callback.message.edit_text("Вы уверены, что хотите удалить этот спот?", reply_markup=keyboard)
    await state.set_state(CheckinState.confirming_delete)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_spot_handler(callback: types.CallbackQuery, state: FSMContext):
    """Удаление спота после подтверждения."""
    user_id = callback.from_user.id
    if not await is_admin(user_id):  # Добавляем await
        await callback.answer("❌ У вас нет прав для удаления спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    await delete_spot(spot_id)  # Добавляем await
    logging.info(f"Админ {user_id} удалил спот ID {spot_id}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text("\u2705 Спот удалён!", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "cancel_delete")
async def cancel_delete_spot(callback: types.CallbackQuery, state: FSMContext):
    """Отмена удаления спота."""
    user_id = callback.from_user.id
    spots = await get_spots() or []  # Добавляем await
    if spots:
        keyboard = create_spot_keyboard(spots, await is_admin(user_id))  # Добавляем await для is_admin
        await callback.message.edit_text("Выберите спот для чекаина:", reply_markup=keyboard)
        await state.set_state(CheckinState.choosing_spot)
    else:
        await callback.message.edit_text("\U0001F50D Похоже, рядом нет спотов. \nОтправьте свою геолокацию, чтобы создать новый.")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await callback.message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

# Блок 4: Обработчики для добавления нового спота
@checkin_router.callback_query(F.data == "add_spot")
async def request_location(callback: types.CallbackQuery, state: FSMContext):
    """Просим отправить геолокацию для создания спота."""
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} выбрал добавить новый спот")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.delete()
    await callback.message.answer("\u2705 Отправьте свою геолокацию, чтобы создать новый спот.", reply_markup=keyboard)
    await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.message(CheckinState.adding_spot, F.location)
async def process_location(message: types.Message, state: FSMContext):
    """Обрабатываем геолокацию и просим ввести название спота."""
    lat, lon = message.location.latitude, message.location.longitude
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} отправил геолокацию: {lat}, {lon}")
    await state.update_data(lat=lat, lon=lon)
    await message.answer("📍 Геолокация получена! Теперь введите название спота:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CheckinState.naming_spot)

@checkin_router.message(CheckinState.adding_spot)
async def handle_invalid_location(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не геолокацию."""
    await message.answer("❌ Пожалуйста, отправьте геолокацию, нажав на кнопку '📍 Отправить геолокацию'.")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Normalize below:", reply_markup=keyboard)

@checkin_router.message(CheckinState.naming_spot, F.text)
async def add_new_spot_handler(message: types.Message, state: FSMContext, bot: Bot):
    """Создаём новый спот и предлагаем отметиться"""
    spot_name = message.text.strip()
    if not spot_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    lat, lon = data["lat"], data["lon"]
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} создаёт спот '{spot_name}' с координатами: {lat}, {lon}")

    # Создаем спот
    spot_id = await add_spot(spot_name, lat, lon, creator_id=user_id)
    
    # Сохраняем ID спота в состоянии
    await state.update_data(spot_id=spot_id)
    
    # Предлагаем выбрать действие
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отметиться сейчас", callback_data="checkin_new_spot")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await message.answer(
        f"\u2705 Спот '{spot_name}' успешно создан!\n"
        "Хотите отметить свое присутствие на споте?",
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.choosing_spot)  # Устанавливаем состояние выбора спота
    await state.update_data(new_spot_created=True)  # Флаг, что спот только что создан

@checkin_router.callback_query(F.data == "checkin_new_spot")
async def handle_new_spot_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Обработка чекина на только что созданном споте"""
    data = await state.get_data()
    spot_id = data.get("spot_id")
    
    if not spot_id:
        await callback.answer("❌ Ошибка: спот не найден")
        return
        
    # Показываем карту спота
    spot = await get_spot_by_id(spot_id)
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    
    # Запускаем стандартный процесс выбора типа чекина
    keyboard = create_checkin_type_keyboard()
    await callback.message.answer(
        f"Вы создали спот: {spot['name']}\nВыберите действие:", 
        reply_markup=keyboard
    )
    await state.set_state(CheckinState.selecting_checkin_type)
    await callback.answer()

@checkin_router.message(CheckinState.naming_spot)
async def handle_invalid_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не текст."""
    await message.answer("❌ Пожалуйста, введите название спота текстом.")

# Блок 5: Обработчики для навигации и разчекина
@checkin_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возвращаемся в главное меню."""
    user_id = callback.from_user.id
    await callback.message.delete()
    # Используем await для получения результата функции get_main_keyboard
    reply_markup = await get_main_keyboard(user_id)
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=reply_markup)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data == "uncheckin")
async def process_uncheckin(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатываем разчекин пользователя."""
    user_id = callback.from_user.id
    active_checkin = await get_active_checkin(user_id)  # Добавляем await
    
    if not active_checkin:
        await callback.message.edit_text("❌ Вы еще не отметились на споте.")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
            ]
        )
        await callback.message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await callback.answer()
        return

    # Разчекиниваем пользователя
    await checkout_user(active_checkin["id"])  # Добавляем await
    spot = await get_spot_by_id(active_checkin["spot_id"])  # Добавляем await
    await callback.message.edit_text(f"\u2705 Вы покинули спот '{spot['name']}'! 🚪")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    reply_markup = await get_main_keyboard(user_id)
    await callback.message.answer("Вернитесь в меню:", reply_markup=reply_markup)
    await state.clear()
    await callback.answer()