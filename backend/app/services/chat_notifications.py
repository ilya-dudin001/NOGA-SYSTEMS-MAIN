"""Persistent Telegram outbox для структурированных упоминаний в чате."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db import SessionLocal
from app.db.models import (
    ChatMention,
    ChatMessage,
    ChatRoomKind,
    ChatTelegramStatus,
)
from app.services import chat as chat_service
from app.services.chat import ChatError

logger = logging.getLogger(__name__)

CLAIM_BATCH_SIZE = 20
STALE_LOCK_SECONDS = 5 * 60
RETRY_DELAYS_SECONDS = (5, 30, 120, 600, 1800, 7200, 21600)


@dataclass(frozen=True)
class PreparedNotification:
    mention_id: int
    chat_id: int
    text: str
    url: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def chat_deep_link(webapp_url: str, room_id: int, message_id: int) -> str:
    parts = urlsplit(webapp_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["chat_room"] = str(room_id)
    query["chat_message"] = str(message_id)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


async def claim_due_mentions(
    session: AsyncSession,
    settings: Settings,
    *,
    now: Optional[datetime] = None,
    batch_size: int = CLAIM_BATCH_SIZE,
) -> list[int]:
    """Восстанавливает stale locks и атомарно помечает due batch как sending."""
    current = now or utc_now()
    stale_before = current - timedelta(seconds=STALE_LOCK_SECONDS)

    # Исчерпавшие лимит записи больше не должны бесконечно возвращаться в очередь.
    await session.execute(
        update(ChatMention)
        .where(
            ChatMention.telegram_status.in_(
                (ChatTelegramStatus.pending, ChatTelegramStatus.retry)
            ),
            ChatMention.telegram_attempts >= settings.chat_notify_max_attempts,
        )
        .values(
            telegram_status=ChatTelegramStatus.failed,
            telegram_locked_at=None,
            telegram_next_retry_at=None,
            telegram_last_error="max_attempts_exceeded",
        )
    )
    await session.execute(
        update(ChatMention)
        .where(
            ChatMention.telegram_status == ChatTelegramStatus.sending,
            ChatMention.telegram_locked_at.is_not(None),
            ChatMention.telegram_locked_at < stale_before,
            ChatMention.telegram_attempts < settings.chat_notify_max_attempts,
        )
        .values(
            telegram_status=ChatTelegramStatus.retry,
            telegram_locked_at=None,
            telegram_next_retry_at=current,
            telegram_last_error="stale_lock_recovered",
        )
    )
    await session.execute(
        update(ChatMention)
        .where(
            ChatMention.telegram_status == ChatTelegramStatus.sending,
            ChatMention.telegram_locked_at.is_not(None),
            ChatMention.telegram_locked_at < stale_before,
            ChatMention.telegram_attempts >= settings.chat_notify_max_attempts,
        )
        .values(
            telegram_status=ChatTelegramStatus.failed,
            telegram_locked_at=None,
            telegram_next_retry_at=None,
            telegram_last_error="max_attempts_exceeded",
        )
    )

    due = (
        await session.execute(
            select(ChatMention.id)
            .where(
                ChatMention.telegram_status.in_(
                    (ChatTelegramStatus.pending, ChatTelegramStatus.retry)
                ),
                ChatMention.telegram_attempts < settings.chat_notify_max_attempts,
                or_(
                    ChatMention.telegram_next_retry_at.is_(None),
                    ChatMention.telegram_next_retry_at <= current,
                ),
            )
            .order_by(ChatMention.id.asc())
            .limit(max(1, batch_size))
        )
    ).scalars().all()

    claimed: list[int] = []
    for mention_id in due:
        result = await session.execute(
            update(ChatMention)
            .where(
                ChatMention.id == mention_id,
                ChatMention.telegram_status.in_(
                    (ChatTelegramStatus.pending, ChatTelegramStatus.retry)
                ),
                or_(
                    ChatMention.telegram_next_retry_at.is_(None),
                    ChatMention.telegram_next_retry_at <= current,
                ),
            )
            .values(
                telegram_status=ChatTelegramStatus.sending,
                telegram_attempts=ChatMention.telegram_attempts + 1,
                telegram_locked_at=current,
                telegram_next_retry_at=None,
                telegram_last_error=None,
            )
        )
        if result.rowcount == 1:
            claimed.append(int(mention_id))
    await session.commit()
    return claimed


async def _cancel_invalid(
    session: AsyncSession, mention: ChatMention, reason: str
) -> None:
    mention.telegram_status = ChatTelegramStatus.cancelled
    mention.telegram_locked_at = None
    mention.telegram_next_retry_at = None
    mention.telegram_last_error = reason[:500]
    await session.commit()


async def prepare_notification(
    session: AsyncSession,
    mention_id: int,
    settings: Settings,
) -> Optional[PreparedNotification]:
    """Повторно валидирует outbox row непосредственно перед Telegram API."""
    mention = await session.scalar(
        select(ChatMention)
        .where(ChatMention.id == mention_id)
        .options(
            selectinload(ChatMention.user),
            selectinload(ChatMention.message).selectinload(ChatMessage.room),
        )
        .execution_options(populate_existing=True)
    )
    if mention is None or mention.telegram_status != ChatTelegramStatus.sending:
        return None

    message = mention.message
    user = mention.user
    if user is None or mention.user_id is None:
        await _cancel_invalid(session, mention, "user_missing")
        return None
    if message is None or message.deleted_at is not None:
        await _cancel_invalid(session, mention, "message_deleted")
        return None
    if message.author_id is not None and message.author_id == user.id:
        await _cancel_invalid(session, mention, "self_mention")
        return None

    room = message.room
    try:
        await chat_service.assert_room_access(session, user, room)
    except ChatError:
        await _cancel_invalid(session, mention, "access_revoked")
        return None

    room_title = room.title or "Чат"
    if room.kind == ChatRoomKind.direct:
        peer = await chat_service.find_direct_peer(session, room, user.id)
        room_title = peer.display_name if peer is not None else "Диалог"

    return PreparedNotification(
        mention_id=mention.id,
        chat_id=user.telegram_id,
        text=f"{message.author_name} упомянул вас в чате «{room_title}»",
        url=chat_deep_link(settings.webapp_url, room.id, message.id),
    )


async def mark_sent(
    session: AsyncSession, mention_id: int, *, now: Optional[datetime] = None
) -> None:
    await session.execute(
        update(ChatMention)
        .where(
            ChatMention.id == mention_id,
            ChatMention.telegram_status == ChatTelegramStatus.sending,
        )
        .values(
            telegram_status=ChatTelegramStatus.sent,
            telegram_sent_at=now or utc_now(),
            telegram_locked_at=None,
            telegram_next_retry_at=None,
            telegram_last_error=None,
        )
    )
    await session.commit()


async def mark_failed_or_retry(
    session: AsyncSession,
    mention_id: int,
    settings: Settings,
    *,
    terminal: bool,
    retry_after: Optional[int] = None,
    error_name: str,
    now: Optional[datetime] = None,
) -> None:
    mention = await session.get(ChatMention, mention_id)
    if mention is None or mention.telegram_status != ChatTelegramStatus.sending:
        return
    current = now or utc_now()
    exhausted = mention.telegram_attempts >= settings.chat_notify_max_attempts
    if terminal or exhausted:
        mention.telegram_status = ChatTelegramStatus.failed
        mention.telegram_next_retry_at = None
    else:
        index = max(0, min(mention.telegram_attempts - 1, len(RETRY_DELAYS_SECONDS) - 1))
        delay = retry_after if retry_after is not None else RETRY_DELAYS_SECONDS[index]
        mention.telegram_status = ChatTelegramStatus.retry
        mention.telegram_next_retry_at = current + timedelta(seconds=max(1, delay))
    mention.telegram_locked_at = None
    mention.telegram_last_error = error_name[:500]
    await session.commit()
    logger.info(
        "chat.notification.%s mention_id=%s attempts=%s error=%s",
        mention.telegram_status.value,
        mention_id,
        mention.telegram_attempts,
        error_name,
    )


def notification_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть чат",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


async def process_claimed_mention(
    bot: Bot,
    mention_id: int,
    settings: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> None:
    async with session_factory() as session:
        prepared = await prepare_notification(session, mention_id, settings)
    if prepared is None:
        return

    try:
        await bot.send_message(
            chat_id=prepared.chat_id,
            text=prepared.text,
            parse_mode=None,
            reply_markup=notification_keyboard(prepared.url),
        )
    except TelegramRetryAfter as exc:
        async with session_factory() as session:
            await mark_failed_or_retry(
                session,
                mention_id,
                settings,
                terminal=False,
                retry_after=exc.retry_after,
                error_name=type(exc).__name__,
            )
    except (
        TelegramForbiddenError,
        TelegramNotFound,
        TelegramBadRequest,
    ) as exc:
        async with session_factory() as session:
            await mark_failed_or_retry(
                session,
                mention_id,
                settings,
                terminal=True,
                error_name=type(exc).__name__,
            )
    except (
        TelegramNetworkError,
        TelegramServerError,
        TelegramUnauthorizedError,
        asyncio.TimeoutError,
        OSError,
    ) as exc:
        async with session_factory() as session:
            await mark_failed_or_retry(
                session,
                mention_id,
                settings,
                terminal=False,
                error_name=type(exc).__name__,
            )
    except Exception as exc:
        logger.exception(
            "chat.notification.unexpected mention_id=%s error=%s",
            mention_id,
            type(exc).__name__,
        )
        async with session_factory() as session:
            await mark_failed_or_retry(
                session,
                mention_id,
                settings,
                terminal=False,
                error_name=type(exc).__name__,
            )
    else:
        async with session_factory() as session:
            await mark_sent(session, mention_id)
        logger.info("chat.notification.sent mention_id=%s", mention_id)


async def run_notification_worker(
    bot: Bot,
    settings: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> None:
    """Один persistent worker; безопасно отменяется lifecycle через task.cancel()."""
    logger.info("chat.notification.worker_started")
    try:
        while True:
            try:
                async with session_factory() as session:
                    claimed = await claim_due_mentions(session, settings)
                for mention_id in claimed:
                    await process_claimed_mention(
                        bot,
                        mention_id,
                        settings,
                        session_factory=session_factory,
                    )
                if not claimed:
                    await asyncio.sleep(settings.chat_notify_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("chat.notification.worker_error")
                await asyncio.sleep(settings.chat_notify_poll_seconds)
    finally:
        logger.info("chat.notification.worker_stopped")

