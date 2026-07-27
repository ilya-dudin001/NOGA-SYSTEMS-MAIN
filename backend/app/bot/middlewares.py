from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User, UserStatus


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class UserResolveMiddleware(BaseMiddleware):
    """Resolve DB user from Telegram sender; put into data['db_user']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        tg_user: Optional[TgUser] = data.get("event_from_user")
        db_user: Optional[User] = None
        if tg_user is not None:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            db_user = result.scalar_one_or_none()
        data["db_user"] = db_user
        data["is_allowed"] = bool(
            db_user is not None and db_user.status == UserStatus.active
        )
        return await handler(event, data)
