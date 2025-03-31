from aiogram import Router, types
from aiogram.filters import Command
from keyboards import get_main_keyboard  # Импортируем динамическую клавиатуру
from database import get_user, add_or_update_user  # Импортируем функции для работы с пользователями

start_router = Router()

@start_router.message(Command("start"))
async def start_command(message: types.Message):
    # Удаляем старую клавиатуру (если была) и отправляем приветственное сообщение
    await message.answer("⏳ Обновляем клавиатуру...", reply_markup=types.ReplyKeyboardRemove())

    # Регистрируем пользователя, если он ещё не в базе
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        add_or_update_user(
            user_id=user_id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            username=message.from_user.username
        )

    # Формируем текст приветственного сообщения
    welcome_text = (
        "👋 Привет, {name}!\n\n"
        "Я – бот проекта *Я на споте* 🏄‍♂️🌬️\n\n"
        "📍 *Помогу тебе спланировать каталку на кайте!* \n\n"
        "✅ Покажу ближайшие к тебе споты с подходящим ветром 🌬️\n"
        "✅ Расскажу, где уже зачекинились кайтеры или кто собирается 🚀\n"
        "✅ Дам актуальный прогноз погоды по выбранным спотам ☀️🌊\n"
        "✅ Позволю отмечать своё местоположение и видеть других кайтсерферов на карте 🗺️\n\n"
        "📲 Выбирай команду ниже или напиши мне!"
    ).format(name=message.from_user.full_name)

    # Отправляем сообщение с динамической клавиатурой
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))