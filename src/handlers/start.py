from aiogram import Router, types
from aiogram.filters import Command
from keyboards import main_keyboard  # Импортируем клавиатуру

start_router = Router()

@start_router.message(Command("start"))
async def start_command(message: types.Message):
    # Удаляем старую клавиатуру (если была) и отправляем приветственное сообщение
    await message.answer("⏳ Обновляем клавиатуру...", reply_markup=types.ReplyKeyboardRemove())

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

    # Отправляем сообщение с клавиатурой
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard)
