from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .config import get_settings

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    web_app_url = getattr(settings, "web_app_url", "")
    if not web_app_url:
        raise RuntimeError("WEB_APP_URL is not configured")

    bot = Bot(settings.bot_token)
    dispatcher = Dispatcher()

    @dispatcher.message(CommandStart())
    async def start(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Открыть личный кабинет", web_app=WebAppInfo(url=web_app_url)
        )]])
        await message.answer(
            "Добро пожаловать! Откройте приложение, чтобы подтвердить профиль и увидеть расписание.",
            reply_markup=keyboard,
        )

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

