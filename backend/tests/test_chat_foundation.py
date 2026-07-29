"""Chat foundation smoke: migration cycle and idempotent bootstrap.

Run from backend/: python tests/test_chat_foundation.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sqlite3
import sys

TEST_DB = pathlib.Path("data/test_chat_foundation.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_chat_foundation.db"
os.environ["OWNER_TELEGRAM_IDS"] = ""

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


def chat_table_names() -> set[str]:
    with sqlite3.connect(TEST_DB) as db:
        return {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'chat_%'"
            )
        }


def assert_seed_rooms() -> None:
    with sqlite3.connect(TEST_DB) as db:
        rows = db.execute(
            """
            SELECT slug, title, kind, sort_order
            FROM chat_rooms ORDER BY sort_order, id
            """
        ).fetchall()
    assert rows == [
        ("general", "Общий", "system", 10),
        ("team", "Команда", "system", 20),
    ], rows


async def assert_bootstrap_idempotent() -> None:
    from sqlalchemy import func, select

    from app.db import SessionLocal, engine
    from app.db.bootstrap import bootstrap_chat_rooms
    from app.db.models import ChatRoom, ChatRoomKind

    async with SessionLocal() as session:
        await bootstrap_chat_rooms(session)
        await bootstrap_chat_rooms(session)
        count = await session.scalar(
            select(func.count())
            .select_from(ChatRoom)
            .where(ChatRoom.kind == ChatRoomKind.system)
        )
        assert count == 2, count
    await engine.dispose()


def main() -> None:
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    expected = {
        "chat_rooms",
        "chat_room_members",
        "chat_messages",
        "chat_attachments",
        "chat_mentions",
        "chat_reads",
        "chat_events",
    }
    assert chat_table_names() == expected
    assert_seed_rooms()

    command.downgrade(config, "006_trubki")
    assert chat_table_names() == set()

    command.upgrade(config, "head")
    assert chat_table_names() == expected
    assert_seed_rooms()

    asyncio.run(assert_bootstrap_idempotent())
    assert_seed_rooms()
    print("CHAT FOUNDATION TESTS PASSED")


if __name__ == "__main__":
    main()
