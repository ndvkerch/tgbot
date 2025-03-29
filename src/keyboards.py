from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Основная клавиатура с кнопками
main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📍 Чек-ин", callback_data="checkin")],
    [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
])

