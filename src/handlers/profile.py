import logging
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_user, get_active_checkin, get_spots, get_checkins_for_user, get_favorite_spots, add_favorite_spot, remove_favorite_spot, get_spot_by_id
from keyboards import get_main_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)
profile_router = Router()

# Определение состояний для FSM
class ProfileState(StatesGroup):
    managing_favorites = State()

# Блок 1: Вспомогательные функции
async def create_favorite_spots_keyboard(user_id: int, spots: list) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком спотов для управления избранным."""
    keyboard = []
    favorite_spots = await get_favorite_spots(user_id)
    favorite_spot_ids = set(favorite_spots)  # Исправлено: работаем с списком int

    for spot in spots:
        spot_id = spot["id"]
        if spot_id in favorite_spot_ids:
            button_text = f"{spot['name']} (удалить из избранного)"
            callback_data = f"remove_favorite_{spot_id}"
        else:
            button_text = f"{spot['name']} (добавить в избранное)"
            callback_data = f"add_favorite_{spot_id}"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Блок 2: Обработчики профиля (остальные функции без изменений)
@profile_router.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден. Попробуйте перезапустить бота с помощью /start.")
        await callback.answer()
        return

    checkins = await get_checkins_for_user(user_id)
    total_time_hours = sum(checkin["duration_hours"] or 0 for checkin in checkins)

    active_checkin = await get_active_checkin(user_id)
    active_spot_text = "Нет активного чек-ина."
    if active_checkin:
        spot = await get_spot_by_id(active_checkin["spot_id"])
        active_spot_text = f"Вы сейчас на споте: {spot['name']}"

    profile_text = (
        f"👤 Профиль пользователя {user['first_name']}:\n\n"
        f"📊 Статистика:\n"
        f"Всего чек-инов: {len(checkins)}\n"
        f"Общее время на спотах: {total_time_hours:.1f} часов\n\n"
        f"📍 Текущий спот:\n{active_spot_text}\n\n"
        f"⭐ Управление избранными спотами:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Управлять избранными спотами", callback_data="manage_favorites")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(profile_text, reply_markup=keyboard)
    await callback.answer()

@profile_router.callback_query(F.data == "manage_favorites")
async def manage_favorite_spots(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    spots = await get_spots() or []

    if not spots:
        await callback.message.edit_text("❌ В базе нет спотов для добавления в избранное.")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="back_to_profile")]
            ]
        )
        await callback.message.answer("Вернитесь в профиль:", reply_markup=keyboard)
        await state.clear()
        await callback.answer()
        return

    keyboard = await create_favorite_spots_keyboard(user_id, spots)
    await callback.message.edit_text("Выберите спот для управления избранным:", reply_markup=keyboard)
    await state.set_state(ProfileState.managing_favorites)
    await callback.answer()

@profile_router.callback_query(F.data.startswith("add_favorite_"))
async def add_favorite_spot_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    spot_id = int(callback.data.split("_")[-1])  # Исправлено: извлекаем последний элемент
    try:
        await add_favorite_spot(user_id, spot_id)
        logging.info(f"Пользователь {user_id} добавил спот ID {spot_id} в избранное")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await callback.answer("❌ Не удалось добавить в избранное")
        return

    spots = await get_spots() or []
    keyboard = await create_favorite_spots_keyboard(user_id, spots)
    await callback.message.edit_text("Спот добавлен в избранное! Выберите другой спот или вернитесь в профиль:", reply_markup=keyboard)
    await callback.answer()

@profile_router.callback_query(F.data.startswith("remove_favorite_"))
async def remove_favorite_spot_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    spot_id = int(callback.data.split("_")[-1])  # Исправлено: извлекаем последний элемент
    try:
        await remove_favorite_spot(user_id, spot_id)
        logging.info(f"Пользователь {user_id} удалил спот ID {spot_id} из избранного")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await callback.answer("❌ Не удалось удалить из избранного")
        return

    spots = await get_spots() or []
    keyboard = await create_favorite_spots_keyboard(user_id, spots)
    await callback.message.edit_text("Спот удалён из избранного! Выберите другой спот или вернитесь в профиль:", reply_markup=keyboard)
    await callback.answer()

@profile_router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery, state: FSMContext):
    """Возвращает пользователя в профиль из управления избранным."""
    user_id = callback.from_user.id
    user = await get_user(user_id)  # Добавляем await
    if not user:
        await callback.message.answer("❌ Пользователь не найден. Попробуйте перезапустить бота с помощью /start.")
        await callback.answer()
        return

    # Получаем статистику чек-инов
    checkins = await get_checkins_for_user(user_id)  # Добавляем await
    total_time_hours = 0
    for checkin in checkins:
        if checkin["duration_hours"]:
            total_time_hours += checkin["duration_hours"]

    # Получаем текущий активный спот
    active_checkin = await get_active_checkin(user_id)  # Добавляем await
    active_spot_text = "Нет активного чек-ина."
    if active_checkin:
        spot = await get_spot_by_id(active_checkin["spot_id"])  # Добавляем await
        active_spot_text = f"Вы сейчас на споте: {spot['name']}"

    # Формируем текст профиля
    profile_text = (
        f"👤 Профиль пользователя {user['first_name']}:\n\n"
        f"📊 Статистика:\n"
        f"Всего чек-инов: {len(checkins)}\n"
        f"Общее время на спотах: {total_time_hours:.1f} часов\n\n"
        f"📍 Текущий спот:\n{active_spot_text}\n\n"
        f"⭐ Управление избранными спотами:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Управлять избранными спотами", callback_data="manage_favorites")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(profile_text, reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@profile_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возвращает пользователя в главное меню."""
    user_id = callback.from_user.id
    await callback.message.delete()
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard(user_id))
    await state.clear()
    await callback.answer()