import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_spot_by_id
from services.weather import get_windy_forecast, wind_direction_to_text

logging.basicConfig(level=logging.INFO)
weather_router = Router()

class WeatherState(StatesGroup):
    selecting_spot = State()

@weather_router.callback_query(F.data == "weather")
async def request_weather(callback: types.CallbackQuery, state: FSMContext):
    """Запрашивает выбор спота для прогноза погоды."""
    await callback.message.answer("Выберите спот для получения прогноза ветра:")
    # Здесь можно добавить клавиатуру с выбором спотов, как в checkin.py
    # Для примера предполагаем, что спот уже выбран и передан в состоянии
    await state.set_state(WeatherState.selecting_spot)
    await callback.answer()

@weather_router.callback_query(F.data.startswith("spot_"), WeatherState.selecting_spot)
async def process_weather_request(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает запрос погоды для выбранного спота."""
    spot_id = int(callback.data.split("_")[1])
    spot = await get_spot_by_id(spot_id)
    
    if not spot:
        await callback.message.answer("❌ Спот не найден.")
        await state.clear()
        await callback.answer()
        return
    
    # Запрашиваем данные о ветре
    wind_data = await get_windy_forecast(spot["lat"], spot["lon"])
    if not wind_data:
        await callback.message.answer("❌ Не удалось получить данные о ветре.")
        await state.clear()
        await callback.answer()
        return
    
    # Формируем ответ
    wind_speed = wind_data["speed"]
    wind_direction = wind_data["direction"]
    direction_text = wind_direction_to_text(wind_direction)
    response = (
        f"🌬 Прогноз ветра для спота '{spot['name']}':\n"
        f"Скорость: {wind_speed:.1f} м/с\n"
        f"Направление: {direction_text} ({wind_direction:.0f}°)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.answer(response, reply_markup=keyboard)
    await state.clear()
    await callback.answer()