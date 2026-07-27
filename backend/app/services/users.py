from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.initdata import TelegramUser
from app.auth.permissions import ROLE_LABELS_RU, permissions_for
from app.db.models import AuthAttempt, User, UserStatus
from app.schemas import MeOut


def user_to_me(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
        permissions=permissions_for(user.role),
        role_label=ROLE_LABELS_RU.get(user.role, user.role.value),
    )


async def log_auth_attempt(
    session: AsyncSession,
    *,
    telegram_id: Optional[int],
    success: bool,
    reason: str,
) -> None:
    session.add(
        AuthAttempt(telegram_id=telegram_id, success=success, reason=reason)
    )


async def get_active_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def touch_last_seen(session: AsyncSession, user: User) -> None:
    user.last_seen_at = datetime.now(timezone.utc)
    if user.first_name is None and user.display_name:
        pass


async def sync_profile_from_telegram(user: User, tg: TelegramUser) -> None:
    if tg.username:
        user.username = tg.username
    if tg.first_name:
        user.first_name = tg.first_name
        # Keep custom display_name if it looks intentionally set; otherwise sync
        if user.display_name in ("Owner", "", None) or user.display_name == user.first_name:
            user.display_name = tg.first_name
