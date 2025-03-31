from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

class BotMiddleware(BaseMiddleware):
    """Middleware для передачи объекта bot в обработчики."""
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def __call__(self, handler, event, data):
        data["bot"] = self.bot
        return await handler(event, data)