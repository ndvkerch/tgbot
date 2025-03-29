from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery

profile_router = Router()

@profile_router.message(Command("profile"))
async def profile_command(message: types.Message):
    user = message.from_user
    profile_text = (
        f"👤 Профиль пользователя:\n"
        f"🔹 Имя: {user.first_name}\n"
        f"🔹 ID: {user.id}\n"
        f"🔹 Юзернейм: @{user.username}" if user.username else "❌ Нет юзернейма"
    )
    await message.answer(profile_text)

@profile_router.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user = callback.from_user
    profile_text = (
        f"👤 Профиль пользователя:\n"
        f"🔹 Имя: {user.first_name}\n"
        f"🔹 ID: {user.id}\n"
        f"🔹 Юзернейм: @{user.username}" if user.username else "❌ Нет юзернейма"
    )
    await callback.message.answer(profile_text)
    await callback.answer()
