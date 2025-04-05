from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_active_checkin, get_spots

async def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Генерирует динамическую клавиатуру в зависимости от состояния пользователя."""
    # Базовые кнопки, которые всегда видны
    buttons = [
        [InlineKeyboardButton(text="📍 Отметиться на споте", callback_data="checkin")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ]

    # Проверяем, есть ли активный чек-ин
    active_checkin = await get_active_checkin(user_id)
    if active_checkin:
        if active_checkin["checkin_type"] == 1:
            # Если пользователь уже на споте
            buttons.append([InlineKeyboardButton(text="🚪 Покинуть спот", callback_data="uncheckin")])
        elif active_checkin["checkin_type"] == 2:
            # Если пользователь запланировал приезд
            buttons.append([InlineKeyboardButton(text="✅ Я приехал", callback_data="confirm_arrival")])

    # Проверяем, есть ли споты в базе, и добавляем кнопки
    spots = await get_spots()
    if spots:
        buttons.append([InlineKeyboardButton(text="🔍 Кто на спотах", callback_data="nearby_spots")])
        buttons.append([InlineKeyboardButton(text="🌤️ Ближайшие споты", callback_data="weather_nearby_spots")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)