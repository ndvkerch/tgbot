import logging
import math
from datetime import datetime

from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_spots, get_spot_by_id, get_active_checkin, get_checkins_for_spot

logging.basicConfig(level=logging.INFO)
spots_router = Router()

class NearbySpotsState(StatesGroup):
    waiting_for_location = State()

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками на Земле (в километрах) с помощью формулы гаверсинуса."""
    R = 6371  # Радиус Земли в километрах
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


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
    """Обрабатываем геолокацию и показываем 5 ближайших спотов."""
    user_lat = message.location.latitude
    user_lon = message.location.longitude
    spots = await get_spots() or []  # Добавили await

    if not spots:
        await message.answer("❌ Похоже, в базе нет спотов.", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
            ]
        )
        await message.answer("Вернитесь в меню:", reply_markup=keyboard)
        await state.clear()
        return

    # Вычисляем расстояния до всех спотов
    distances = [
        (spot, haversine_distance(user_lat, user_lon, spot["lat"], spot["lon"]))
        for spot in spots
    ]
    # Сортируем по расстоянию и берём 5 ближайших
    nearest_spots = sorted(distances, key=lambda x: x[1])[:5]

    # Формируем ответ
    response = "🔍 Ближайшие споты:\n\n"
    for spot, distance in nearest_spots:
        on_spot_count, on_spot_users, arriving_users = await get_checkins_for_spot(spot["id"])  # Добавили await
        on_spot_names = ", ".join(user["first_name"] for user in on_spot_users) if on_spot_users else "никого"
        arriving_info = ", ".join(f"{user['first_name']} ({user['arrival_time']})" for user in arriving_users) if arriving_users else "нет"
        response += (
            f"Спот: {spot['name']}\n"
            f"Расстояние: {distance:.2f} км\n"
            f"На месте: {on_spot_count} чел. ({on_spot_names})\n"
            f"Приедут: {len(arriving_users)} чел. ({arriving_info})\n\n"
        )

    await message.answer(response, reply_markup=ReplyKeyboardRemove())
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await message.answer("Вернитесь в меню:", reply_markup=keyboard)
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