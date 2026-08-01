import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.initdata import TelegramUser
from app.auth.permissions import (
    CHAT_READ,
    ROLE_LABELS_RU,
    USERS_DELETE,
    has_permission,
    permissions_for,
)
from app.config import get_settings
from app.db.models import (
    AuditLog,
    AuthAttempt,
    ChatAttachment,
    ChatEvent,
    ChatMention,
    ChatMessage,
    ChatRead,
    ChatRoomMember,
    ChatTelegramStatus,
    TrubkaEvent,
    TrubkaFile,
    User,
    UserRole,
    UserStatus,
)
from app.schemas import FeaturesOut, MeOut
from app.services.audit import write_audit


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
        features=FeaturesOut(
            chat=get_settings().chat_enabled and has_permission(user.role, CHAT_READ)
        ),
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


def sync_profile_from_telegram(user: User, tg: TelegramUser) -> None:
    if tg.username:
        user.username = tg.username
    if tg.first_name:
        user.first_name = tg.first_name
        # Keep custom display_name if it looks intentionally set; otherwise sync
        if user.display_name in ("Owner", "", None) or user.display_name == user.first_name:
            user.display_name = tg.first_name


class UserActionError(Exception):
    """Domain error surfaced both to the API (as HTTP detail) and to the bot (as text)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


DISPLAY_NAME_MIN = 2
DISPLAY_NAME_MAX = 32
# Ник — кириллица, латиница и цифры; пробел, дефис и подчёркивание разрешены как
# разделители, чтобы не ломать уже заведённые имена вида «Иван Петров».
DISPLAY_NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z0-9]+([ _-][А-Яа-яЁёA-Za-z0-9]+)*$")
DISPLAY_NAME_HINT = (
    "Ник может состоять из русских и английских букв, цифр, "
    "пробела, дефиса и подчёркивания"
)


def normalize_display_name(value: Optional[str]) -> str:
    """Чистит и проверяет ник. Кидает UserActionError, как остальные действия сервиса."""
    name = " ".join((value or "").split())
    if len(name) < DISPLAY_NAME_MIN:
        raise UserActionError(
            "BAD_REQUEST", f"Ник должен быть не короче {DISPLAY_NAME_MIN} символов"
        )
    if len(name) > DISPLAY_NAME_MAX:
        raise UserActionError(
            "BAD_REQUEST", f"Ник должен быть не длиннее {DISPLAY_NAME_MAX} символов"
        )
    if not DISPLAY_NAME_RE.match(name):
        raise UserActionError("BAD_REQUEST", DISPLAY_NAME_HINT)
    return name


async def rename_self(session: AsyncSession, *, actor: User, display_name: str) -> User:
    name = normalize_display_name(display_name)
    if name == actor.display_name:
        return actor
    await write_audit(
        session,
        action="user.renamed",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(actor.id),
        payload={"from": actor.display_name, "to": name},
    )
    actor.display_name = name
    await session.commit()
    await session.refresh(actor)
    return actor


async def delete_user_account(
    session: AsyncSession,
    *,
    actor: User,
    target: User,
    via: str,
) -> dict:
    if not has_permission(actor.role, USERS_DELETE):
        raise UserActionError("FORBIDDEN", "Недостаточно прав для удаления пользователей")
    if target.id == actor.id:
        raise UserActionError("BAD_REQUEST", "Нельзя удалить себя")
    if target.role == UserRole.owner:
        owners = await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.owner)
        )
        if (owners or 0) <= 1:
            raise UserActionError("BAD_REQUEST", "Нельзя удалить последнего Owner")

    snapshot = {
        "telegram_id": target.telegram_id,
        "display_name": target.display_name,
        "role": target.role.value,
        "status": target.status.value,
        "actor_telegram_id": actor.telegram_id,
        "via": via,
    }

    # Drop references to the row before removing it: PostgreSQL enforces these FKs,
    # and stale ids would survive silently on SQLite.
    await session.execute(
        update(User).where(User.created_by_id == target.id).values(created_by_id=None)
    )
    await session.execute(
        update(AuditLog).where(AuditLog.actor_user_id == target.id).values(actor_user_id=None)
    )
    await session.execute(
        update(ChatMessage)
        .where(ChatMessage.author_id == target.id)
        .values(author_id=None)
    )
    await session.execute(
        update(ChatMessage)
        .where(ChatMessage.deleted_by_id == target.id)
        .values(deleted_by_id=None)
    )
    await session.execute(
        update(ChatAttachment)
        .where(ChatAttachment.uploaded_by_id == target.id)
        .values(uploaded_by_id=None)
    )
    await session.execute(
        update(TrubkaFile)
        .where(TrubkaFile.uploaded_by_id == target.id)
        .values(uploaded_by_id=None)
    )
    await session.execute(
        update(TrubkaEvent)
        .where(TrubkaEvent.actor_user_id == target.id)
        .values(actor_user_id=None)
    )
    # Историю уже завершённых доставок сохраняем. Отменяются только ещё
    # не отправленные уведомления, затем user_id снимается со всех упоминаний.
    await session.execute(
        update(ChatMention)
        .where(
            ChatMention.user_id == target.id,
            ChatMention.telegram_status.in_(
                (ChatTelegramStatus.pending, ChatTelegramStatus.retry)
            ),
        )
        .values(
            telegram_status=ChatTelegramStatus.cancelled,
            telegram_next_retry_at=None,
            telegram_locked_at=None,
        )
    )
    await session.execute(
        update(ChatMention)
        .where(ChatMention.user_id == target.id)
        .values(user_id=None)
    )
    await session.execute(delete(ChatRead).where(ChatRead.user_id == target.id))
    await session.execute(
        delete(ChatRoomMember).where(ChatRoomMember.user_id == target.id)
    )
    # Targeted events must be deleted, not made public by setting target_user_id to NULL.
    await session.execute(
        delete(ChatEvent).where(ChatEvent.target_user_id == target.id)
    )

    await write_audit(
        session,
        action="user.deleted",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(target.id),
        payload=snapshot,
    )
    await session.delete(target)
    await session.commit()
    return snapshot
