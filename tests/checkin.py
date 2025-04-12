@checkin_router.callback_query(F.data.startswith("duration_"), CheckinState.confirming_arrival)
async def process_arrival_duration(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатываем длительность после подтверждения прибытия."""
    duration_str = callback.data.split("_")[1]
    duration_hours = float(duration_str) if duration_str in ["1", "2", "3"] else None
    
    if duration_str.startswith("until_"):
        target_hour = int(duration_str.split("_")[1].split(":")[0])
        now = datetime.utcnow()
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target_time < now:
            target_time += timedelta(days=1)
        duration_hours = (target_time - now).total_seconds() / 3600

    data = await state.get_data()
    checkin_id = data["checkin_id"]
    spot_id = data.get("spot_id")
    
    # Обновляем чек-ин: переводим в тип 1 и задаём длительность
    await update_checkin_to_arrived(checkin_id, duration_hours)
    
    # Получаем информацию о споте для отображения на карте
    active_checkin = await get_active_checkin(callback.from_user.id)
    spot = await get_spot_by_id(spot_id or active_checkin["spot_id"])
    
    # Добавляем клавиатуру прямо в отредактированное сообщение
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Разчекиниться", callback_data="uncheckin")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(
        f"\u2705 Вы прибыли и отметились на споте '{spot['name']}'! 🌊",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()