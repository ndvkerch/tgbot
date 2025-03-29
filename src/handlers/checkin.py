import logging

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, add_spot, checkin_user, update_spot_name, delete_spot
from keyboards import main_keyboard

logging.basicConfig(level=logging.INFO)
checkin_router = Router()

# ID администратора (замените на ваш user.id)
ADMIN_ID = 1478148696  # Укажите ваш Telegram ID

class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()
    naming_spot = State()
    editing_spot = State()  # Новое состояние для редактирования названия спота

def is_admin(user_id: int) -> bool:
    """Проверяем, является ли пользователь админом."""
    return user_id == ADMIN_ID

def create_spot_keyboard(spots: list, is_admin: bool) -> InlineKeyboardMarkup:
    """Создаём клавиатуру со списком спотов, с доп. кнопками для админа."""
    keyboard = []
    for spot in spots:
        spot_buttons = [InlineKeyboardButton(text=spot["name"], callback_data=f"spot_{spot['id']}")]
        if is_admin:
            # Добавляем кнопки редактирования и удаления для админа
            spot_buttons.append(InlineKeyboardButton(text="✏️", callback_data=f"edit_spot_{spot['id']}"))
            spot_buttons.append(InlineKeyboardButton(text="🗑️", callback_data=f"delete_spot_{spot['id']}"))
        keyboard.append(spot_buttons)
    # Кнопка "Добавить новый спот"
    keyboard.append([InlineKeyboardButton(text="➕ Добавить новый спот", callback_data="add_spot")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующего спота или добавление нового."""
    logging.info(f"Пользователь {callback.from_user.id} нажал на Чек-ин (callback)")
    spots = get_spots() or []  # Безопасная проверка

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
    """Начало редактирования названия спота (только для админа)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав для редактирования спотов.", show_alert=True)
        return

    spot_id = int(callback.data.split("_")[2])
    await state.update_data(spot_id=spot_id)
    await callback.message.answer("✏️ Введите новое название для спота:")
    await state.set_state(CheckinState.editing_spot)
    await callback.answer()

@checkin_router.message(CheckinState.editing_spot, F.text)
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

@checkin_router.message(CheckinState.editing_spot)
async def handle_invalid_new_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если админ отправил не текст."""
    await message.answer("❌ Пожалуйста, введите новое название спота текстом.")

@checkin_router.callback_query(F.data.startswith("delete_spot_"))
async def delete_spot_handler(callback: types.CallbackQuery, state: FSMContext):
    """Удаление спота (только для админа)."""
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