from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import router as bot_router
from app.bot.middlewares import DbSessionMiddleware, UserResolveMiddleware
from app.config import Settings
from app.db import SessionLocal

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp["settings"] = settings
    dp.update.middleware(DbSessionMiddleware(SessionLocal))
    dp.update.middleware(UserResolveMiddleware())
    dp.include_router(bot_router)
    return dp


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть NOGA"),
            BotCommand(command="whoami", description="Кто я"),
            BotCommand(command="users", description="Список пользователей"),
            BotCommand(command="adduser", description="Добавить пользователя"),
            BotCommand(command="setrole", description="Сменить роль"),
            BotCommand(command="block", description="Заблокировать"),
            BotCommand(command="unblock", description="Разблокировать"),
            BotCommand(command="deleteuser", description="Удалить пользователя"),
        ]
    )


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await setup_bot_commands(bot)
    logger.info("Starting bot polling…")
    # Bot общий с notification worker; сессию закрывает только app lifespan.
    await dp.start_polling(bot, handle_signals=False, close_bot_session=False)


def ensure_data_dir(database_url: str) -> None:
    # sqlite+aiosqlite:///./data/noga.db
    if "sqlite" not in database_url:
        return
    path_part = database_url.split("///")[-1]
    db_path = Path(path_part)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
