"""Telegram outbox smoke. Run from backend/: python tests/test_chat_notifications.py"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage
from sqlalchemy import select

TEST_DB = pathlib.Path("data/test_chat_notifications.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_TOKEN"] = "123456:TEST_TOKEN"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long"
os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_chat_notifications.db"
os.environ["OWNER_TELEGRAM_IDS"] = ""
os.environ["CHAT_ENABLED"] = "true"
os.environ["CHAT_TELEGRAM_NOTIFICATIONS_ENABLED"] = "true"
os.environ["CHAT_NOTIFY_MAX_ATTEMPTS"] = "3"
os.environ["WEBAPP_URL"] = "https://example.test/app?source=telegram"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.db.bootstrap import bootstrap_chat_rooms  # noqa: E402
from app.db.models import (  # noqa: E402
    ChatMention,
    ChatMessage,
    ChatRoom,
    ChatTelegramStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import chat as chat_service  # noqa: E402
from app.services import chat_notifications as notifications  # noqa: E402

get_settings.cache_clear()


class MockBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    async def send_message(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return object()


async def setup() -> tuple[int, int, int]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await bootstrap_chat_rooms(session)
        owner = User(
            telegram_id=101,
            display_name="Иван Петров",
            role=UserRole.owner,
            status=UserStatus.active,
        )
        admin = User(
            telegram_id=202,
            display_name="Анна",
            role=UserRole.admin,
            status=UserStatus.active,
        )
        session.add_all([owner, admin])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(admin)
        room_id = int(
            await session.scalar(select(ChatRoom.id).where(ChatRoom.slug == "team"))
        )
        return owner.id, admin.id, room_id


async def create_mention(owner_id: int, admin_id: int, room_id: int, label: str) -> int:
    async with SessionLocal() as session:
        owner = await session.get(User, owner_id)
        assert owner is not None
        message = await chat_service.create_message(
            session,
            owner,
            room_id,
            content_raw=[
                {"type": "text", "text": f"Секретный текст {label} "},
                {"type": "mention", "user_id": admin_id},
            ],
        )
        mention_id = await session.scalar(
            select(ChatMention.id).where(ChatMention.message_id == message["id"])
        )
        assert mention_id is not None
        return int(mention_id)


async def claim_one(mention_id: int) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        claimed = await notifications.claim_due_mentions(session, settings)
    assert mention_id in claimed


async def mention_row(mention_id: int) -> ChatMention:
    async with SessionLocal() as session:
        row = await session.get(ChatMention, mention_id)
        assert row is not None
        session.expunge(row)
        return row


async def test_success(owner_id: int, admin_id: int, room_id: int) -> None:
    mention_id = await create_mention(owner_id, admin_id, room_id, "success")
    await claim_one(mention_id)
    bot = MockBot()
    await notifications.process_claimed_mention(bot, mention_id, get_settings())

    row = await mention_row(mention_id)
    assert row.telegram_status == ChatTelegramStatus.sent
    assert row.telegram_sent_at is not None
    assert row.telegram_locked_at is None
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call["chat_id"] == 202
    assert call["text"] == "Иван Петров упомянул вас в чате «Команда»"
    assert "Секретный" not in call["text"]
    button = call["reply_markup"].inline_keyboard[0][0]
    query = parse_qs(urlsplit(button.web_app.url).query)
    assert query == {
        "source": ["telegram"],
        "chat_room": [str(room_id)],
        "chat_message": [str(row.message_id)],
    }
    await notifications.process_claimed_mention(bot, mention_id, get_settings())
    assert len(bot.calls) == 1


async def test_network_retry(owner_id: int, admin_id: int, room_id: int) -> None:
    mention_id = await create_mention(owner_id, admin_id, room_id, "network")
    await claim_one(mention_id)
    error = TelegramNetworkError(
        method=SendMessage(chat_id=202, text="safe"),
        message="network",
    )
    await notifications.process_claimed_mention(
        MockBot(error), mention_id, get_settings()
    )
    row = await mention_row(mention_id)
    assert row.telegram_status == ChatTelegramStatus.retry
    assert row.telegram_attempts == 1
    assert row.telegram_next_retry_at is not None
    assert row.telegram_last_error == "TelegramNetworkError"
    async with SessionLocal() as session:
        assert await session.get(ChatMessage, row.message_id) is not None


async def test_retry_after(owner_id: int, admin_id: int, room_id: int) -> None:
    mention_id = await create_mention(owner_id, admin_id, room_id, "retry-after")
    await claim_one(mention_id)
    before = datetime.now(timezone.utc)
    error = TelegramRetryAfter(
        method=SendMessage(chat_id=202, text="safe"),
        message="flood",
        retry_after=77,
    )
    await notifications.process_claimed_mention(
        MockBot(error), mention_id, get_settings()
    )
    row = await mention_row(mention_id)
    retry_at = row.telegram_next_retry_at
    assert retry_at is not None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    assert retry_at >= before + timedelta(seconds=76)


async def test_terminal_failure(owner_id: int, admin_id: int, room_id: int) -> None:
    mention_id = await create_mention(owner_id, admin_id, room_id, "terminal")
    await claim_one(mention_id)
    error = TelegramForbiddenError(
        method=SendMessage(chat_id=202, text="safe"),
        message="forbidden",
    )
    await notifications.process_claimed_mention(
        MockBot(error), mention_id, get_settings()
    )
    row = await mention_row(mention_id)
    assert row.telegram_status == ChatTelegramStatus.failed
    assert row.telegram_next_retry_at is None


async def test_stale_recovery(owner_id: int, admin_id: int, room_id: int) -> None:
    mention_id = await create_mention(owner_id, admin_id, room_id, "stale")
    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with SessionLocal() as session:
        row = await session.get(ChatMention, mention_id)
        assert row is not None
        row.telegram_status = ChatTelegramStatus.sending
        row.telegram_attempts = 1
        row.telegram_locked_at = stale
        await session.commit()
    await claim_one(mention_id)
    row = await mention_row(mention_id)
    assert row.telegram_status == ChatTelegramStatus.sending
    assert row.telegram_attempts == 2


async def test_deleted_and_blocked_cancel(
    owner_id: int, admin_id: int, room_id: int
) -> None:
    pending_id = await create_mention(owner_id, admin_id, room_id, "pending-delete")
    async with SessionLocal() as session:
        mention = await session.get(ChatMention, pending_id)
        assert mention is not None
        owner = await session.get(User, owner_id)
        assert owner is not None
        assert await chat_service.soft_delete_message(
            session, owner, mention.message_id
        )
    assert (await mention_row(pending_id)).telegram_status == ChatTelegramStatus.cancelled

    deleted_id = await create_mention(owner_id, admin_id, room_id, "deleted")
    await claim_one(deleted_id)
    async with SessionLocal() as session:
        mention = await session.get(ChatMention, deleted_id)
        assert mention is not None
        message = await session.get(ChatMessage, mention.message_id)
        assert message is not None
        message.deleted_at = datetime.now(timezone.utc)
        await session.commit()
    bot = MockBot()
    await notifications.process_claimed_mention(
        bot, deleted_id, get_settings()
    )
    assert (await mention_row(deleted_id)).telegram_status == ChatTelegramStatus.cancelled
    assert bot.calls == []

    blocked_id = await create_mention(owner_id, admin_id, room_id, "blocked")
    await claim_one(blocked_id)
    async with SessionLocal() as session:
        admin = await session.get(User, admin_id)
        assert admin is not None
        admin.status = UserStatus.blocked
        await session.commit()
    bot = MockBot()
    await notifications.process_claimed_mention(
        bot, blocked_id, get_settings()
    )
    assert (await mention_row(blocked_id)).telegram_status == ChatTelegramStatus.cancelled
    assert bot.calls == []


async def main() -> None:
    owner_id, admin_id, room_id = await setup()
    await test_success(owner_id, admin_id, room_id)
    await test_network_retry(owner_id, admin_id, room_id)
    await test_retry_after(owner_id, admin_id, room_id)
    await test_terminal_failure(owner_id, admin_id, room_id)
    await test_stale_recovery(owner_id, admin_id, room_id)
    await test_deleted_and_blocked_cancel(owner_id, admin_id, room_id)
    await engine.dispose()
    print("CHAT NOTIFICATION TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

