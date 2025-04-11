import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import get_active_checkin, get_spots, get_favorite_spots

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    Генерирует динамическую клавиатуру в зависимости от состояния пользователя.
    
    Используется в: start.py, checkin.py, profile.py, spots.py, weather.py (через back_to_menu).
    
    Args:
        user_id (int): ID пользователя.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с динамическими кнопками.
    """
    logger.debug(f"Генерация главной клавиатуры для пользователя {user_id}")
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    logger.debug(f"Создана главная клавиатура для пользователя {user_id}: {buttons}")
    return keyboard

def create_spot_keyboard(spots: list, is_admin: bool) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру со списком спотов, с дополнительными кнопками для админа.
    
    Используется в: checkin.py.
    
    Args:
        spots (list): Список спотов.
        is_admin (bool): Является ли пользователь админом.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура со списком спотов.
    """
    logger.debug(f"Создание клавиатуры спотов, is_admin={is_admin}")
    keyboard = []
    for spot in spots:
        spot_buttons = [InlineKeyboardButton(text=spot["name"], callback_data=f"spot_{spot['id']}")]
        if is_admin:
            spot_buttons.append(InlineKeyboardButton(text="✏️", callback_data=f"edit_spot_{spot['id']}"))
            spot_buttons.append(InlineKeyboardButton(text="🗑️", callback_data=f"delete_spot_{spot['id']}"))
        keyboard.append(spot_buttons)
    keyboard.append([InlineKeyboardButton(text="➕ Добавить новый спот", callback_data="add_spot")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")])
    logger.debug(f"Создана клавиатура спотов: {keyboard}")
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_checkin_type_keyboard(spot_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора типа чек-ина.
    
    Используется в: checkin.py.
    
    Args:
        spot_id (int): ID выбранного спота.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с типами чек-ина.
    """
    logger.debug(f"Создание клавиатуры для выбора типа чек-ина с spot_id={spot_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я на споте", callback_data="checkin_type_1")],
        [InlineKeyboardButton(text="Планирую приехать", callback_data=f"plan_to_arrive_{spot_id}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])
    logger.debug(f"Создана клавиатура для выбора типа чек-ина: {keyboard.inline_keyboard}")
    return keyboard

def create_duration_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора длительности пребывания.
    
    Используется в: checkin.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с вариантами длительности.
    """
    logger.debug("Создание клавиатуры для выбора длительности")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 час", callback_data="duration_1"),
         InlineKeyboardButton(text="2 часа", callback_data="duration_2"),
         InlineKeyboardButton(text="3 часа", callback_data="duration_3")],
        [InlineKeyboardButton(text="4 часа", callback_data="duration_4"),
         InlineKeyboardButton(text="5 часов", callback_data="duration_5"),
         InlineKeyboardButton(text="6 часов", callback_data="duration_6")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])
    logger.debug(f"Создана клавиатура для выбора длительности: {keyboard.inline_keyboard}")
    return keyboard

def create_arrival_time_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора времени прибытия.
    
    Используется в: checkin.py, spots.py, weather.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с вариантами времени прибытия.
    """
    logger.debug("Создание клавиатуры для выбора времени прибытия")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 1 час", callback_data="arrival_1"),
         InlineKeyboardButton(text="Через 2 часа", callback_data="arrival_2"),
         InlineKeyboardButton(text="Через 3 часа", callback_data="arrival_3")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_checkin")]
    ])
    logger.debug(f"Создана клавиатура для выбора времени прибытия: {keyboard.inline_keyboard}")
    return keyboard

def create_arrival_confirmation_keyboard(checkin_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для подтверждения прибытия.
    
    Используется в: checkin.py.
    
    Args:
        checkin_id (int): ID чек-ина.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для подтверждения/отмены прибытия.
    """
    logger.debug(f"Создание клавиатуры подтверждения прибытия для checkin_id={checkin_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я на месте", callback_data=f"late_arrival_confirm_{checkin_id}")],
        [InlineKeyboardButton(text="🚪 Отмена", callback_data=f"cancel_late_arrival_{checkin_id}")]
    ])
    logger.debug(f"Создана клавиатура подтверждения прибытия: {keyboard.inline_keyboard}")
    return keyboard

def create_location_request_keyboard() -> ReplyKeyboardMarkup:
    """
    Создаёт клавиатуру с запросом геолокации.
    
    Используется в: checkin.py, spots.py, weather.py.
    
    Returns:
        ReplyKeyboardMarkup: Клавиатура с кнопкой отправки геолокации.
    """
    logger.debug("Создание клавиатуры для запроса геолокации")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    logger.debug("Создана клавиатура для запроса геолокации")
    return keyboard

def create_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой возврата в меню.
    
    Используется в: checkin.py, spots.py, profile.py, weather.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой "Назад в меню".
    """
    logger.debug("Создание клавиатуры для возврата в меню")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    logger.debug(f"Создана клавиатура для возврата в меню: {keyboard.inline_keyboard}")
    return keyboard

def create_confirm_delete_keyboard(spot_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для подтверждения удаления спота.
    
    Используется в: checkin.py.
    
    Args:
        spot_id (int): ID спота.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для подтверждения удаления.
    """
    logger.debug(f"Создание клавиатуры подтверждения удаления для spot_id={spot_id}")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{spot_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
        ]
    )
    logger.debug(f"Создана клавиатура подтверждения удаления: {keyboard.inline_keyboard}")
    return keyboard

def create_checkin_new_spot_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для чек-ина на новом споте.
    
    Используется в: checkin.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для чек-ина на новом споте.
    """
    logger.debug("Создание клавиатуры для чек-ина на новом споте")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отметиться сейчас", callback_data="checkin_new_spot")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    logger.debug(f"Создана клавиатура для чек-ина на новом споте: {keyboard.inline_keyboard}")
    return keyboard

def create_uncheckin_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для разчекина.
    
    Используется в: checkin.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для разчекина.
    """
    logger.debug("Создание клавиатуры для разчекина")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Покинуть спот", callback_data="uncheckin")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    logger.debug(f"Создана клавиатура для разчекина: {keyboard.inline_keyboard}")
    return keyboard

def create_confirm_arrival_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для подтверждения прибытия.
    
    Используется в: checkin.py, spots.py, weather.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для подтверждения прибытия.
    """
    logger.debug("Создание клавиатуры для подтверждения прибытия")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я приехал!", callback_data="confirm_arrival")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    logger.debug(f"Создана клавиатура для подтверждения прибытия: {keyboard.inline_keyboard}")
    return keyboard

def create_nearby_spots_keyboard(spots: list) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для ближайших активных спотов.
    
    Используется в: spots.py.
    
    Args:
        spots (list): Список кортежей (spot, distance) с активными спотами.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками для планирования приезда.
    """
    logger.debug("Создание клавиатуры для ближайших активных спотов")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"plan_to_arrive_{spot['id']}")]
            for spot, distance in spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )
    logger.debug(f"Создана клавиатура для ближайших активных спотов: {keyboard.inline_keyboard}")
    return keyboard

async def create_favorite_spots_keyboard(user_id: int, spots: list) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру со списком спотов для управления избранным.
    
    Используется в: profile.py.
    
    Args:
        user_id (int): ID пользователя.
        spots (list): Список спотов.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура для управления избранными спотами.
    """
    logger.debug(f"Создание клавиатуры избранных спотов для пользователя {user_id}")
    keyboard = []
    favorite_spots = await get_favorite_spots(user_id)
    favorite_spot_ids = set(favorite_spots)

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
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard)
    logger.debug(f"Создана клавиатура избранных спотов: {keyboard.inline_keyboard}")
    return keyboard

def create_profile_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для профиля пользователя.
    
    Используется в: profile.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура профиля.
    """
    logger.debug("Создание клавиатуры профиля")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Управлять избранными спотами", callback_data="manage_favorites")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    logger.debug(f"Создана клавиатура профиля: {keyboard.inline_keyboard}")
    return keyboard

def create_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой возврата в профиль.
    
    Используется в: profile.py.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой "Назад в профиль".
    """
    logger.debug("Создание клавиатуры для возврата в профиль")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="back_to_profile")]
        ]
    )
    logger.debug(f"Создана клавиатура для возврата в профиль: {keyboard.inline_keyboard}")
    return keyboard

def create_weather_spots_keyboard(spots: list) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для ближайших спотов с погодой.
    
    Используется в: weather.py.
    
    Args:
        spots (list): Список кортежей (spot, distance) с ближайшими спотами.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками для планирования приезда.
    """
    logger.debug("Создание клавиатуры для ближайших спотов с погодой")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏄‍♂️ Собираюсь на {spot['name']}", callback_data=f"plan_to_arrive_{spot['id']}")]
            for spot, distance in spots
        ] + [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]]
    )
    logger.debug(f"Создана клавиатура для ближайших спотов с погодой: {keyboard.inline_keyboard}")
    return keyboard