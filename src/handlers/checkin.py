import logging

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, add_spot, checkin_user
from keyboards import main_keyboard  # Импортируем главную клавиатуру

logging.basicConfig(level=logging.INFO)
checkin_router = Router()

class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()
    naming_spot = State()  # Новое состояние для ввода названия спота

@checkin_router.callback_query(F.data == "checkin")
async def process_checkin(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующего спота или добавление нового."""
    logging.info(f"Пользователь {callback.from_user.id} нажал на Чек-ин (callback)")
    spots = get_spots() or []  # Безопасная проверка

    if spots:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=spot["name"], callback_data=f"spot_{spot['id']}")] for spot in spots
            ] + [[InlineKeyboardButton(text="➕ Добавить новый спот", callback_data="add_spot")]]
        )
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
    # Добавляем кнопку "Назад" в главное меню
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text("\u2705 Вы зачекинились! 🌊", reply_markup=keyboard)
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
    # Сохраняем координаты в состоянии
    await state.update_data(lat=lat, lon=lon)
    # Убираем клавиатуру с кнопкой геолокации
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

    # Получаем координаты из состояния
    data = await state.get_data()
    lat, lon = data["lat"], data["lon"]
    logging.info(f"Пользователь {message.from_user.id} создаёт спот '{spot_name}' с координатами: {lat}, {lon}")
    
    # Создаём спот с введённым названием
    spot_id = add_spot(spot_name, lat, lon)
    checkin_user(message.from_user.id, spot_id)
    
    # Добавляем кнопку "Назад" в главное меню
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await message.answer(f"\u2705 Спот '{spot_name}' создан!\nТеперь вы зачекинились здесь. 🌊", reply_markup=keyboard)
    await state.clear()

@checkin_router.message(CheckinState.naming_spot)
async def handle_invalid_spot_name(message: types.Message, state: FSMContext):
    """Обрабатываем случай, если пользователь отправил не текст (например, фото)."""
    await message.answer("❌ Пожалуйста, введите название спота текстом.")

@checkin_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возвращаемся в главное меню."""
    await callback.message.delete()
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=main_keyboard)
    await state.clear()
    await callback.answer()