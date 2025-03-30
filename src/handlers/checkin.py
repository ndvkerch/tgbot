import logging

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, add_spot, checkin_user, update_spot_name, update_spot_location, delete_spot
from keyboards import main_keyboard

logging.basicConfig(level=logging.INFO)
checkin_router = Router()

# ID администратора (уже исправлен)
ADMIN_ID = 1478148696  # Убедитесь, что это ваш ID

class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()
    naming_spot = State()
    editing_location = State()
    editing_name = State()
    confirming_delete = State()

def is_admin(user_id: int) -> bool:
    """Проверяем, является ли пользователь админом."""
    result = user_id == ADMIN_ID
    logging.info(f"Проверка: пользователь {user_id} является админом? {result}")
    return result

def create_spot_keyboard(spots: list, is_admin: bool) -> InlineKeyboardMarkup:
    """Создаём клавиатуру со списком спотов, с доп. кнопками для админа."""
    logging.info(f"Создаём клавиатуру для спотов. Количество спотов: {len(spots)}, is_admin: {is_admin}")
    keyboard = []
    for spot in spots:
        logging.info(f"Обрабатываем спот: {spot}")
        spot_buttons = [InlineKeyboardButton(text=spot["name"], callback_data=f"spot_{spot['id']}")]
        if is_admin:
            logging.info(f"Добавляем кнопки редактирования и удаления для спота ID={spot['id']}")
            spot_buttons.append(InlineKeyboardButton(text="✏️", callback_data=f"edit_spot_{spot['id']}"))
            spot_buttons.append(InlineKeyboardButton(text="🗑️", callback_data=f"delete_spot_{spot['id']}"))
        keyboard.append(spot_buttons)
    keyboard.append([InlineKeyboardButton(text="➕ Добавить новый спот", callback_data="add_spot")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующего спота или добавление нового."""
    logging.info(f"Пользователь {callback.from_user.id} нажал на Чек-ин (callback)")
    spots = get_spots() or []  # Безопасная проверка
    logging.info(f"Получены споты: {spots}")

    if spots:
        keyboard = create_spot_keyboard(spots, is_admin(callback.from_user.id))
        await callback.message.answer("Выберите спот для чекаина:", reply_markup=keyboard)
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
async def checkin_existing_spot(callback: types.CallbackQuery, state: FSMContext):
    """Чекин на существующем споте."""
    logging.info(f"Пользователь {callback.from_user.id} выбрал спот: {callback.data}")
    spot_id = int(callback.data.split("_")[1])
    checkin_user(callback.from_user.id, spot_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text("\u2705 Вы зачекинились! 🌊", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("edit_spot_"))
async def edit_spot(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования спота (только для админа): сначала геопозиция."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав для редактирования спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    # Находим спот, чтобы получить текущую геолокацию
    spots = get_spots()
    spot = next((s for s in spots if s["id"] == spot_id), None)
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await state.clear()
        return

    await state.update_data(spot_id=spot_id)
    # Отправляем текущую геолокацию спота
    await callback.message.answer(f"Текущая геолокация спота '{spot['name']}':")
    await callback.message.answer_location(latitude=spot["lat"], longitude=spot["lon"])
    
    # Запрашиваем новую геолокацию
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
    update_spot_location(spot_id, new_lat, new_lon)
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
    update_spot_name(spot_id, new_name)
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
    if not is_admin(callback.from_user.id):
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
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав для удаления спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    delete_spot(spot_id)
    logging.info(f"Админ {callback.from_user.id} удалил спот ID {spot_id}")

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
    spots = get_spots() or []
    if spots:
        keyboard = create_spot_keyboard(spots, is_admin(callback.from_user.id))
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

@checkin_router.callback_query(F.data == "add_spot")
async def request_location(callback: types.CallbackQuery, state: FSMContext):
    """Просим отправить геолокацию для создания спота."""
    logging.info(f"Пользователь {callback.from_user.id} выбрал добавить новый спот")
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
    logging.info(f"Пользователь {message.from_user.id} отправил геолокацию: {lat}, {lon}")
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
    await message.answer("Нажмите кнопку ниже:", reply_markup=keyboard)

@checkin_router.message(CheckinState.naming_spot, F.text)
async def add_new_spot_handler(message: types.Message, state: FSMContext):
    """Создаём новый спот с введённым названием и чекиним пользователя."""
    spot_name = message.text.strip()
    if not spot_name:
        await message.answer("❌ Название спота не может быть пустым. Пожалуйста, введите название ещё раз:")
        return

    data = await state.get_data()
    lat, lon = data["lat"], data["lon"]
    logging.info(f"Пользователь {message.from_user.id} создаёт спот '{spot_name}' с координатами: {lat}, {lon}")
    
    spot_id = add_spot(spot_name, lat, lon)
    checkin_user(message.from_user.id, spot_id)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await message.answer(f"\u2705 Спот '{spot_name}' создан!\nТеперь вы зачекинились здесь. 🌊", reply_markup=keyboard)
    await state.clear()

@checkin_router.message(CheckinState.naming_spot)
async def handle_invalid_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не текст."""
    await message.answer("❌ Пожалуйста, введите название спота текстом.")

@checkin_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возвращаемся в главное меню."""
    await callback.message.delete()
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=main_keyboard)
    await state.clear()
    await callback.answer()