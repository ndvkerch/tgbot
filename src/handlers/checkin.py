import logging

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, add_spot, checkin_user  # Исправленный импорт

logging.basicConfig(level=logging.INFO)
checkin_router = Router()

class CheckinState(StatesGroup):
    choosing_spot = State()
    adding_spot = State()

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
        await state.set_state(CheckinState.adding_spot)
    await callback.answer()

@checkin_router.callback_query(F.data.startswith("spot_"))
async def checkin_existing_spot(callback: types.CallbackQuery, state: FSMContext):
    """Чекин на существующем споте."""
    logging.info(f"Пользователь {callback.from_user.id} выбрал спот: {callback.data}")
    spot_id = int(callback.data.split("_")[1])
    checkin_user(callback.from_user.id, spot_id)
    await callback.message.edit_text("\u2705 Вы зачекинились! 🌊")
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
async def add_new_spot_handler(message: types.Message, state: FSMContext):
    """Создаем новый спот и чекиним пользователя туда."""
    lat, lon = message.location.latitude, message.location.longitude
    logging.info(f"Пользователь {message.from_user.id} отправил геолокацию: {lat}, {lon}")
    spot_id = add_spot(f"Новый спот {lat:.3f}, {lon:.3f}", lat, lon)
    checkin_user(message.from_user.id, spot_id)
    await message.answer(f"\u2705 Новый спот создан!\nТеперь вы зачекинились здесь. 🌊")
    await state.clear()