from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_active_checkin, get_spots

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Генерирует динамическую клавиатуру в зависимости от состояния пользователя."""
    # Базовые кнопки, которые всегда видны
    buttons = [
        [InlineKeyboardButton(text="📍 Чек-ин", callback_data="checkin")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ]

    # Проверяем, есть ли активный чек-ин
    active_checkin = get_active_checkin(user_id)
    if active_checkin:
        buttons.append([InlineKeyboardButton(text="🚪 Разчекиниться", callback_data="uncheckin")])

    # Проверяем, есть ли споты в базе
    spots = get_spots()
    if spots:
        buttons.append([InlineKeyboardButton(text="🔍 Ближайшие споты", callback_data="nearby_spots")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)