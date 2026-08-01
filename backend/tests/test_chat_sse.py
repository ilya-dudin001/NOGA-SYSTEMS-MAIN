"""Durable SSE/broker smoke. Run from backend/: python tests/test_chat_sse.py"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update

TEST_DB = pathlib.Path("data/test_chat_sse.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_TOKEN"] = "test-token"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long"
os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_chat_sse.db"
os.environ["OWNER_TELEGRAM_IDS"] = ""
os.environ["CHAT_ENABLED"] = "true"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.api.chat import _chat_stream  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.db.bootstrap import bootstrap_chat_rooms  # noqa: E402
from app.db.models import ChatEvent, ChatRoom, User, UserRole, UserStatus  # noqa: E402
from app.services import chat as chat_service  # noqa: E402
from app.services.chat_broker import (  # noqa: E402
    OVERFLOW,
    ChatBroker,
    ChatRateLimiter,
)


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def append_event(event_type: str, room_id: int) -> int:
    async with SessionLocal() as session:
        event = await chat_service.append_event(
            session,
            type=event_type,
            room_id=room_id,
            payload={"sequence": event_type},
        )
        await session.commit()
        event_id = event.id
        assert chat_service.consume_committed_event_ids(session) == [event_id]
        return event_id


async def create_actor_and_room() -> tuple[User, int]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await bootstrap_chat_rooms(session)
        actor = User(
            telegram_id=101,
            display_name="Owner",
            role=UserRole.owner,
            status=UserStatus.active,
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        room_id = int(
            await session.scalar(select(ChatRoom.id).where(ChatRoom.slug == "general"))
        )
        session.expunge(actor)
        return actor, room_id


async def test_replay_live_dedupe_heartbeat(actor: User, room_id: int) -> None:
    settings = get_settings()
    settings.chat_sse_heartbeat_seconds = 0.01
    settings.chat_sse_revalidate_seconds = 60
    broker = ChatBroker(queue_size=10)
    limiter = ChatRateLimiter()
    assert await limiter.acquire_stream(actor.id, limit=3)
    subscription = await broker.subscribe(actor.id)

    first = await append_event("message.created", room_id)
    second = await append_event("message.deleted", room_id)
    await broker.publish(first)
    await broker.publish(second)

    stream = _chat_stream(
        ConnectedRequest(),
        actor=actor,
        room_id=None,
        cursor=0,
        subscription=subscription,
        broker=broker,
        limiter=limiter,
        settings=settings,
    )
    frame1 = await anext(stream)
    frame2 = await anext(stream)
    assert f"id: {first}" in frame1 and "event: message.created" in frame1
    assert f"id: {second}" in frame2 and "event: message.deleted" in frame2

    # Те же ids лежат в live queue: generator дедуплицирует их и доходит до heartbeat.
    heartbeat = await asyncio.wait_for(anext(stream), timeout=0.2)
    assert heartbeat.startswith(": heartbeat ")

    third = await append_event("read.updated", room_id)
    await broker.publish(third)
    live = await asyncio.wait_for(anext(stream), timeout=0.2)
    assert f"id: {third}" in live and "event: read.updated" in live

    await stream.aclose()
    assert broker.subscriber_count == 0


async def test_overflow_and_rate_limit(actor: User) -> None:
    broker = ChatBroker(queue_size=1)
    subscription = await broker.subscribe(actor.id)
    await broker.publish(1)
    await broker.publish(2)
    assert await subscription.queue.get() is OVERFLOW
    await broker.unsubscribe(subscription)

    limiter = ChatRateLimiter()
    assert await limiter.allow("message", actor.id, limit=1, period_seconds=60)
    assert not await limiter.allow("message", actor.id, limit=1, period_seconds=60)
    assert await limiter.acquire_stream(actor.id, limit=1)
    assert not await limiter.acquire_stream(actor.id, limit=1)
    await limiter.release_stream(actor.id)
    assert await limiter.acquire_stream(actor.id, limit=1)
    await limiter.release_stream(actor.id)


async def test_rollback_and_reset(actor: User, room_id: int) -> None:
    async with SessionLocal() as session:
        before = int(
            await session.scalar(select(func.count()).select_from(ChatEvent)) or 0
        )
        await chat_service.append_event(
            session,
            type="message.created",
            room_id=room_id,
            payload={"rolled_back": True},
        )
        await session.rollback()
        chat_service.discard_pending_event_ids(session)
        after = int(
            await session.scalar(select(func.count()).select_from(ChatEvent)) or 0
        )
        assert after == before

        earliest = await session.scalar(select(func.min(ChatEvent.id)))
        assert earliest is not None
        await session.execute(delete(ChatEvent).where(ChatEvent.id == earliest))
        await session.commit()

    settings = get_settings()
    broker = ChatBroker(queue_size=10)
    limiter = ChatRateLimiter()
    assert await limiter.acquire_stream(actor.id, limit=3)
    subscription = await broker.subscribe(actor.id)
    stream = _chat_stream(
        ConnectedRequest(),
        actor=actor,
        room_id=None,
        cursor=0,
        subscription=subscription,
        broker=broker,
        limiter=limiter,
        settings=settings,
    )
    reset = await anext(stream)
    assert "event: stream.reset" in reset
    try:
        await anext(stream)
    except StopAsyncIteration:
        pass
    else:
        raise AssertionError("stream.reset должен закрывать stream")
    assert broker.subscriber_count == 0


async def test_revalidation_revokes(actor: User) -> None:
    settings = get_settings()
    settings.chat_sse_heartbeat_seconds = 0.02
    settings.chat_sse_revalidate_seconds = 0.01
    broker = ChatBroker(queue_size=10)
    limiter = ChatRateLimiter()
    assert await limiter.acquire_stream(actor.id, limit=3)
    subscription = await broker.subscribe(actor.id)

    async with SessionLocal() as session:
        _, latest = await chat_service.event_bounds(session)
    stream = _chat_stream(
        ConnectedRequest(),
        actor=actor,
        room_id=None,
        cursor=int(latest or 0),
        subscription=subscription,
        broker=broker,
        limiter=limiter,
        settings=settings,
    )
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.005)
    async with SessionLocal() as session:
        db_actor = await session.get(User, actor.id)
        assert db_actor is not None
        db_actor.role = UserRole.noga
        await session.commit()
    revoked = await asyncio.wait_for(pending, timeout=0.2)
    assert "event: access.revoked" in revoked
    try:
        await anext(stream)
    except StopAsyncIteration:
        pass
    assert broker.subscriber_count == 0


async def test_event_cleanup() -> None:
    async with SessionLocal() as session:
        event_id = await session.scalar(select(func.min(ChatEvent.id)))
        assert event_id is not None
        await session.execute(
            update(ChatEvent)
            .where(ChatEvent.id == event_id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=10))
        )
        await session.commit()
        deleted = await chat_service.cleanup_expired_events(session, retention_days=7)
        assert deleted == 1
        assert await session.get(ChatEvent, event_id) is None


async def main() -> None:
    actor, room_id = await create_actor_and_room()
    await test_replay_live_dedupe_heartbeat(actor, room_id)
    await test_overflow_and_rate_limit(actor)
    await test_rollback_and_reset(actor, room_id)
    await test_event_cleanup()
    await test_revalidation_revokes(actor)
    await engine.dispose()
    print("CHAT SSE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

