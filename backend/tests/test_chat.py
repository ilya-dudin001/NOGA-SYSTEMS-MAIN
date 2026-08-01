"""Smoke test for chat REST (этапы 2–3: без SSE). Run: python tests/test_chat.py"""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

TEST_DB = pathlib.Path("data/test_chat.db")
UPLOADS = pathlib.Path("data/test_chat_uploads")
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.rmtree(UPLOADS, ignore_errors=True)

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_chat.db"
os.environ["UPLOADS_DIR"] = "./data/test_chat_uploads"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"
os.environ["CHAT_ENABLED"] = "true"
os.environ["CHAT_RATE_MESSAGES_PER_MINUTE"] = "1000"
os.environ["CHAT_RATE_UPLOADS_PER_10_MINUTES"] = "100"
os.environ["CHAT_RATE_DIRECTS_PER_MINUTE"] = "1000"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402
from app.services import chat as chat_service  # noqa: E402

OWNER = 111111111
ADMIN = 333333333
RIGHT = 444444444
NOGA = 222222222
ADMIN2 = 555555555
ADMIN3 = 666666666


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(client: TestClient, telegram_id: int) -> dict[str, str]:
    return {"Authorization": "Bearer " + token(client, telegram_id)}


def send_text(
    client: TestClient,
    headers: dict[str, str],
    room_id: int,
    parts: list,
    *,
    reply_to_id: int | None = None,
) -> Any:
    data = {"content": json.dumps(parts, ensure_ascii=False)}
    if reply_to_id is not None:
        data["reply_to_id"] = str(reply_to_id)
    return client.post(
        f"/api/chat/rooms/{room_id}/messages",
        headers=headers,
        data=data,
    )


def send_files(
    client: TestClient,
    headers: dict[str, str],
    room_id: int,
    parts: list,
    files: list[tuple[str, bytes, str]],
    *,
    reply_to_id: int | None = None,
) -> Any:
    data = {"content": json.dumps(parts, ensure_ascii=False)}
    if reply_to_id is not None:
        data["reply_to_id"] = str(reply_to_id)
    upload = [
        ("files", (name, io.BytesIO(payload), content_type))
        for name, payload, content_type in files
    ]
    return client.post(
        f"/api/chat/rooms/{room_id}/messages",
        headers=headers,
        data=data,
        files=upload,
    )


def count_events() -> int:
    con = sqlite3.connect(TEST_DB)
    try:
        return con.execute("SELECT COUNT(*) FROM chat_events").fetchone()[0]
    finally:
        con.close()


def count_audit(action: str) -> int:
    con = sqlite3.connect(TEST_DB)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ?", (action,)
        ).fetchone()[0]
    finally:
        con.close()


def chat_disk_files() -> list[pathlib.Path]:
    root = UPLOADS / "chat"
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and "_staging" not in p.parts]


def staging_files() -> list[pathlib.Path]:
    root = UPLOADS / "chat" / "_staging"
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file()]


def main() -> None:
    with TestClient(app) as client:
        owner = auth(client, OWNER)

        for tid, role, name in (
            (ADMIN, "admin", "Admin One"),
            (RIGHT, "right_hand", "Right Hand"),
            (NOGA, "noga", "Nora"),
            (ADMIN2, "admin", "Admin Two"),
            (ADMIN3, "admin", "Admin Three"),
        ):
            r = client.post(
                "/api/users",
                headers=owner,
                json={"telegram_id": tid, "role": role, "display_name": name},
            )
            assert r.status_code == 201, r.text

        admin = auth(client, ADMIN)
        right = auth(client, RIGHT)
        noga = auth(client, NOGA)
        admin2 = auth(client, ADMIN2)
        admin3 = auth(client, ADMIN3)

        owner_me = client.get("/api/me", headers=owner).json()
        admin_me = client.get("/api/me", headers=admin).json()
        noga_me = client.get("/api/me", headers=noga).json()
        assert owner_me["features"]["chat"] is True
        assert admin_me["features"]["chat"] is True
        assert noga_me["features"]["chat"] is False

        # --- Роль noga: 403 на каждый chat endpoint ---
        for method, path, kwargs in (
            ("get", "/api/chat/rooms", {}),
            ("get", "/api/chat/peers", {}),
            ("get", "/api/chat/stream", {}),
            ("post", "/api/chat/direct", {"json": {"peer_user_id": owner_me["id"]}}),
            ("get", "/api/chat/mentions", {}),
        ):
            r = getattr(client, method)(path, headers=noga, **kwargs)
            assert r.status_code == 403, (path, r.text)
            assert r.json()["detail"]["code"] == "CHAT_FORBIDDEN"
        print("noga denied on chat endpoints ok")

        # --- Системные комнаты ---
        r = client.get("/api/chat/rooms", headers=owner)
        assert r.status_code == 200, r.text
        rooms_payload = r.json()
        slugs = {room["slug"] for room in rooms_payload["rooms"] if room["kind"] == "system"}
        assert slugs == {"general", "team"}, slugs
        general = next(x for x in rooms_payload["rooms"] if x["slug"] == "general")
        team = next(x for x in rooms_payload["rooms"] if x["slug"] == "team")
        assert general["title"] == "Общий"
        assert team["title"] == "Команда"
        print("system rooms ok")

        # Остальные chat endpoints тоже закрыты для роли noga.
        for method, path, kwargs in (
            ("get", f"/api/chat/rooms/{general['id']}/messages", {}),
            (
                "post",
                f"/api/chat/rooms/{general['id']}/messages",
                {"data": {"content": '[{"type":"text","text":"x"}]'}},
            ),
            ("delete", "/api/chat/messages/1", {}),
            (
                "patch",
                f"/api/chat/rooms/{general['id']}/read",
                {"json": {"last_read_message_id": 1}},
            ),
            ("patch", "/api/chat/mentions/1/read", {}),
            ("get", "/api/chat/attachments/1", {}),
        ):
            r = getattr(client, method)(path, headers=noga, **kwargs)
            assert r.status_code == 403, (path, r.text)
            assert r.json()["detail"]["code"] == "CHAT_FORBIDDEN"

        # --- Peers: без себя и без роли noga ---
        r = client.get("/api/chat/peers", headers=owner)
        assert r.status_code == 200, r.text
        peers = r.json()
        peer_ids = {p["id"] for p in peers}
        assert owner_me["id"] not in peer_ids
        assert noga_me["id"] not in peer_ids
        assert admin_me["id"] in peer_ids
        print("peers ok")

        # --- Direct: create + idempotent ---
        r = client.post(
            "/api/chat/direct",
            headers=owner,
            json={"peer_user_id": admin_me["id"]},
        )
        assert r.status_code == 201, r.text
        direct = r.json()
        assert direct["kind"] == "direct"
        assert direct["peer"]["id"] == admin_me["id"]
        assert count_audit("chat.direct.created") == 1

        r = client.post(
            "/api/chat/direct",
            headers=owner,
            json={"peer_user_id": admin_me["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == direct["id"]
        assert count_audit("chat.direct.created") == 1

        r = client.post(
            "/api/chat/direct",
            headers=admin,
            json={"peer_user_id": owner_me["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == direct["id"]

        r = client.post(
            "/api/chat/direct", headers=owner, json={"peer_user_id": owner_me["id"]}
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_SELF_DIRECT"

        r = client.post(
            "/api/chat/direct", headers=owner, json={"peer_user_id": noga_me["id"]}
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_PEER_FORBIDDEN"
        print("direct uniqueness ok")

        # Настоящая гонка двух инициаторов должна дать одну комнату: 201 + 200.
        right_me = client.get("/api/me", headers=right).json()
        admin3_me = client.get("/api/me", headers=admin3).json()

        def create_raced_direct(headers: dict[str, str], peer_id: int) -> Any:
            return client.post(
                "/api/chat/direct",
                headers=headers,
                json={"peer_user_id": peer_id},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (
                pool.submit(create_raced_direct, right, admin3_me["id"]),
                pool.submit(create_raced_direct, admin3, right_me["id"]),
            )
            raced = [future.result() for future in futures]
        assert sorted(r.status_code for r in raced) == [200, 201], [
            (r.status_code, r.text) for r in raced
        ]
        assert len({r.json()["id"] for r in raced}) == 1
        with sqlite3.connect(TEST_DB) as db:
            key = ":".join(map(str, sorted((right_me["id"], admin3_me["id"]))))
            rows = db.execute(
                "SELECT id FROM chat_rooms WHERE direct_key = ?", (key,)
            ).fetchall()
            assert len(rows) == 1, rows
            members = db.execute(
                "SELECT COUNT(*) FROM chat_room_members WHERE room_id = ?",
                (rows[0][0],),
            ).fetchone()[0]
            assert members == 2, members
            raced_room_id = rows[0][0]

        # Неактивный direct скрыт из списков и не возвращается как рабочий.
        with sqlite3.connect(TEST_DB) as db:
            db.execute(
                "UPDATE chat_rooms SET is_active = 0 WHERE id = ?",
                (raced_room_id,),
            )
        r = client.get("/api/chat/rooms", headers=right)
        assert raced_room_id not in {room["id"] for room in r.json()["rooms"]}
        r = client.post(
            "/api/chat/direct",
            headers=right,
            json={"peer_user_id": admin3_me["id"]},
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "CHAT_ROOM_INACTIVE"

        # Запись запрещена, если invariant «ровно два участника» повреждён.
        admin2_me = client.get("/api/me", headers=admin2).json()
        with sqlite3.connect(TEST_DB) as db:
            db.execute(
                "UPDATE chat_rooms SET is_active = 1 WHERE id = ?",
                (raced_room_id,),
            )
            db.execute(
                """
                INSERT INTO chat_room_members (room_id, user_id, joined_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (raced_room_id, admin2_me["id"]),
            )
        r = send_text(
            client,
            right,
            raced_room_id,
            [{"type": "text", "text": "не должно сохраниться"}],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "CHAT_DIRECT_UNAVAILABLE"
        with sqlite3.connect(TEST_DB) as db:
            db.execute(
                "DELETE FROM chat_room_members WHERE room_id = ? AND user_id = ?",
                (raced_room_id, admin2_me["id"]),
            )
        print("direct concurrent race ok")

        # Третий не видит чужой direct
        r = client.get(f"/api/chat/rooms/{direct['id']}/messages", headers=admin2)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_ROOM_FORBIDDEN"

        # --- Текст / reply / mentions ---
        events_before = count_events()
        r = send_text(
            client,
            owner,
            general["id"],
            [
                {"type": "text", "text": "Привет, "},
                {"type": "mention", "user_id": admin_me["id"]},
                {"type": "text", "text": "!"},
            ],
        )
        assert r.status_code == 201, r.text
        msg = r.json()
        assert msg["author"]["is_current_user"] is True
        assert msg["can_delete"] is True
        labels = [p.get("label") for p in msg["content"] if p["type"] == "mention"]
        assert labels == ["Admin One"], labels
        assert count_events() > events_before
        assert count_audit("chat.message.created") >= 1

        # пустое → ошибка, без нового audit/event (счётчик audit не растёт за пустое)
        audit_before = count_audit("chat.message.created")
        ev_before = count_events()
        r = send_text(client, owner, general["id"], [{"type": "text", "text": ""}])
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_EMPTY_MESSAGE"
        assert count_audit("chat.message.created") == audit_before
        assert count_events() == ev_before

        # Сбой после INSERT сообщения откатывает message/event/audit целиком.
        original_append_event = chat_service.append_event

        async def fail_append_event(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("forced event failure")

        chat_service.append_event = fail_append_event
        rollback_marker = "rollback-marker-chat"
        try:
            try:
                send_text(
                    client,
                    owner,
                    general["id"],
                    [{"type": "text", "text": rollback_marker}],
                )
                raise AssertionError("forced failure did not propagate")
            except RuntimeError as exc:
                assert str(exc) == "forced event failure"
        finally:
            chat_service.append_event = original_append_event
        with sqlite3.connect(TEST_DB) as db:
            assert db.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE body = ?",
                (rollback_marker,),
            ).fetchone()[0] == 0
        assert count_audit("chat.message.created") == audit_before
        assert count_events() == ev_before

        r = send_text(
            client,
            admin,
            general["id"],
            [{"type": "text", "text": "Ответ"}],
            reply_to_id=msg["id"],
        )
        assert r.status_code == 201, r.text
        reply = r.json()
        assert reply["reply"]["id"] == msg["id"]
        assert "Привет" in reply["reply"]["preview"]

        # mention в in-app списке у админа
        r = client.get("/api/chat/mentions?unread_only=true", headers=admin)
        assert r.status_code == 200, r.text
        mentions = r.json()
        assert any(m["message_id"] == msg["id"] for m in mentions), mentions
        mention_id = next(m["id"] for m in mentions if m["message_id"] == msg["id"])

        r = client.patch(f"/api/chat/mentions/{mention_id}/read", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["read_at"] is not None
        with sqlite3.connect(TEST_DB) as db:
            # Индивидуальное чтение mention не двигает room cursor.
            assert db.execute(
                "SELECT COUNT(*) FROM chat_reads WHERE room_id = ? AND user_id = ?",
                (general["id"], admin_me["id"]),
            ).fetchone()[0] == 0
            broadcast = db.execute(
                """
                SELECT payload FROM chat_events
                WHERE type = 'message.created' AND room_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (general["id"],),
            ).fetchone()[0]
            payload = json.loads(broadcast)
            # Durable broadcast не содержит флаги, зависящие от получателя.
            assert "can_delete" not in payload["message"], payload
            assert "is_current_user" not in payload["message"]["author"], payload
            targeted = db.execute(
                """
                SELECT target_user_id FROM chat_events
                WHERE type = 'mention.created' AND payload LIKE ?
                """,
                (f'%"message_id": {msg["id"]}%',),
            ).fetchone()
            assert targeted == (admin_me["id"],), targeted
            audit_payload = db.execute(
                """
                SELECT payload FROM audit_log
                WHERE action = 'chat.message.created' AND target_id = ?
                """,
                (str(msg["id"]),),
            ).fetchone()[0]
            assert "Привет" not in audit_payload

        # Повтор mention остаётся в content, но создаёт одну очередь/уведомление.
        r = send_text(
            client,
            owner,
            general["id"],
            [
                {"type": "mention", "user_id": admin_me["id"]},
                {"type": "text", "text": " и снова "},
                {"type": "mention", "user_id": admin_me["id"]},
            ],
        )
        assert r.status_code == 201, r.text
        duplicate_mention_msg = r.json()
        with sqlite3.connect(TEST_DB) as db:
            assert db.execute(
                "SELECT COUNT(*) FROM chat_mentions WHERE message_id = ?",
                (duplicate_mention_msg["id"],),
            ).fetchone()[0] == 1

        # Нельзя упомянуть роль без доступа к чату.
        r = send_text(
            client,
            owner,
            general["id"],
            [{"type": "mention", "user_id": noga_me["id"]}],
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_PEER_FORBIDDEN"

        # Нормализация объединяет соседние text parts.
        r = send_text(
            client,
            owner,
            general["id"],
            [
                {"type": "text", "text": "a"},
                {"type": "text", "text": "b"},
                {"type": "text", "text": ""},
            ],
        )
        assert r.status_code == 201, r.text
        assert r.json()["content"] == [{"type": "text", "text": "ab"}]

        r = send_text(
            client,
            owner,
            general["id"],
            [{"type": "text", "text": "x" * 4000}],
        )
        assert r.status_code == 201, r.text
        r = send_text(
            client,
            owner,
            general["id"],
            [{"type": "text", "text": "x" * 4001}],
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_TEXT_TOO_LONG"

        r = client.post(
            f"/api/chat/rooms/{general['id']}/messages",
            headers=owner,
            data={"content": "{bad json"},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_BAD_CONTENT"

        # Reply обязан ссылаться на сообщение этой же комнаты.
        r = send_text(
            client,
            owner,
            direct["id"],
            [{"type": "text", "text": "wrong room reply"}],
            reply_to_id=msg["id"],
        )
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "CHAT_MESSAGE_NOT_FOUND"

        r = client.delete(f"/api/chat/messages/{msg['id']}", headers=owner)
        assert r.status_code == 204, r.text
        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages"
            f"?around_id={reply['id']}&limit=3",
            headers=admin,
        )
        assert r.status_code == 200, r.text
        reply_after_delete = next(
            item for item in r.json() if item["id"] == reply["id"]
        )
        assert reply_after_delete["reply"]["id"] == msg["id"]
        assert reply_after_delete["reply"]["is_deleted"] is True
        assert reply_after_delete["reply"]["preview"] == "Сообщение удалено"
        print("text/reply/mentions ok")

        # --- Pagination ---
        created_ids = []
        for i in range(5):
            r = send_text(
                client,
                owner,
                general["id"],
                [{"type": "text", "text": f"msg-{i}"}],
            )
            assert r.status_code == 201, r.text
            created_ids.append(r.json()["id"])

        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages?limit=3",
            headers=owner,
        )
        assert r.status_code == 200, r.text
        page = r.json()
        assert len(page) == 3
        assert page[0]["id"] < page[1]["id"] < page[2]["id"]
        oldest_in_page = page[0]["id"]

        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages?before_id={oldest_in_page}&limit=2",
            headers=owner,
        )
        assert r.status_code == 200, r.text
        older = r.json()
        assert len(older) == 2
        assert older[-1]["id"] < oldest_in_page

        pivot = created_ids[2]
        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages?around_id={pivot}&limit=3",
            headers=owner,
        )
        assert r.status_code == 200, r.text
        around = r.json()
        assert any(m["id"] == pivot for m in around)
        assert len(around) == 3
        assert [m["id"] for m in around] == sorted(m["id"] for m in around)
        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages"
            f"?before_id={pivot}&around_id={pivot}",
            headers=owner,
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_BAD_CONTENT"
        print("pagination ok")

        # --- Unread / read cursor ---
        r = send_text(
            client,
            owner,
            general["id"],
            [{"type": "text", "text": "для курсора"}],
        )
        assert r.status_code == 201, r.text
        unread_msg = r.json()

        r = client.get("/api/chat/rooms", headers=admin)
        assert r.status_code == 200, r.text
        admin_rooms = r.json()
        g = next(x for x in admin_rooms["rooms"] if x["id"] == general["id"])
        assert g["unread_count"] >= 1
        assert admin_rooms["total_unread"] >= 1

        r = client.patch(
            f"/api/chat/rooms/{general['id']}/read",
            headers=admin,
            json={"last_read_message_id": unread_msg["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["unread_count"] == 0
        assert r.json()["last_read_message_id"] == unread_msg["id"]

        # Повторный и обратный cursor не создают event/audit и не двигают позицию.
        read_events_before = count_events()
        read_audits_before = count_audit("chat.read.updated")
        for cursor_id in (unread_msg["id"], msg["id"]):
            r = client.patch(
                f"/api/chat/rooms/{general['id']}/read",
                headers=admin,
                json={"last_read_message_id": cursor_id},
            )
            assert r.status_code == 200, r.text
            assert r.json()["last_read_message_id"] == unread_msg["id"]
        assert count_events() == read_events_before
        assert count_audit("chat.read.updated") == read_audits_before

        # После cursor собственное сообщение не считается, чужое считается ровно один раз.
        r = send_text(
            client,
            admin,
            general["id"],
            [{"type": "text", "text": "моё после cursor"}],
        )
        assert r.status_code == 201, r.text
        r = send_text(
            client,
            owner,
            general["id"],
            [{"type": "text", "text": "чужое после cursor"}],
        )
        assert r.status_code == 201, r.text
        foreign_after_cursor = r.json()
        r = client.get("/api/chat/rooms", headers=admin)
        room_state = next(x for x in r.json()["rooms"] if x["id"] == general["id"])
        assert room_state["unread_count"] == 1, room_state

        # Room read закрывает непрочитанные mentions до cursor.
        r = send_text(
            client,
            owner,
            general["id"],
            [
                {"type": "text", "text": "mention after cursor "},
                {"type": "mention", "user_id": admin_me["id"]},
            ],
        )
        assert r.status_code == 201, r.text
        mention_after_cursor = r.json()
        r = client.patch(
            f"/api/chat/rooms/{general['id']}/read",
            headers=admin,
            json={"last_read_message_id": mention_after_cursor["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["unread_count"] == 0
        assert r.json()["unread_mentions"] == 0
        assert r.json()["last_read_message_id"] > foreign_after_cursor["id"]

        # Два конкурентных PATCH не могут оставить меньший cursor.
        cursor_messages = []
        for text in ("cursor-low", "cursor-high"):
            r = send_text(
                client,
                owner,
                general["id"],
                [{"type": "text", "text": text}],
            )
            assert r.status_code == 201, r.text
            cursor_messages.append(r.json()["id"])

        def patch_cursor(message_id: int) -> Any:
            return client.patch(
                f"/api/chat/rooms/{general['id']}/read",
                headers=admin,
                json={"last_read_message_id": message_id},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            cursor_results = list(
                pool.map(patch_cursor, reversed(cursor_messages))
            )
        assert all(r.status_code == 200 for r in cursor_results), [
            (r.status_code, r.text) for r in cursor_results
        ]
        r = client.patch(
            f"/api/chat/rooms/{general['id']}/read",
            headers=admin,
            json={"last_read_message_id": cursor_messages[0]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["last_read_message_id"] == max(cursor_messages)
        print("unread/read ok")

        # --- Delete matrix ---
        r = send_text(
            client,
            admin,
            general["id"],
            [{"type": "text", "text": "своё админа"}],
        )
        assert r.status_code == 201, r.text
        admin_msg = r.json()

        r = send_text(
            client,
            right,
            general["id"],
            [{"type": "text", "text": "своё правой руки"}],
        )
        assert r.status_code == 201, r.text
        right_msg = r.json()

        # admin не удаляет чужое
        r = client.delete(f"/api/chat/messages/{right_msg['id']}", headers=admin)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_DELETE_FORBIDDEN"

        # admin удаляет своё
        r = client.delete(f"/api/chat/messages/{admin_msg['id']}", headers=admin)
        assert r.status_code == 204, r.text
        r = client.delete(f"/api/chat/messages/{admin_msg['id']}", headers=admin)
        assert r.status_code == 204, r.text

        r = client.get(
            f"/api/chat/rooms/{general['id']}/messages?around_id={admin_msg['id']}&limit=5",
            headers=admin,
        )
        stub = next(m for m in r.json() if m["id"] == admin_msg["id"])
        assert stub["is_deleted"] is True
        assert stub["content"] == []
        assert stub["can_delete"] is False

        # owner удаляет чужое
        r = client.delete(f"/api/chat/messages/{right_msg['id']}", headers=owner)
        assert r.status_code == 204, r.text
        print("delete matrix ok")

        # --- Этап 3: безопасные вложения ---

        # file-only
        r = send_files(
            client,
            owner,
            general["id"],
            [],
            [("note.txt", b"hello-file-only", "text/plain")],
        )
        assert r.status_code == 201, r.text
        file_only = r.json()
        assert file_only["content"] == []
        assert len(file_only["attachments"]) == 1
        assert file_only["attachments"][0]["original_name"] == "note.txt"
        assert file_only["attachments"][0]["size_bytes"] == len(b"hello-file-only")
        att_id = file_only["attachments"][0]["id"]

        r = client.get(f"/api/chat/attachments/{att_id}", headers=owner)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/octet-stream")
        assert "nosniff" in r.headers.get("x-content-type-options", "").lower()
        assert "no-store" in r.headers.get("cache-control", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.content == b"hello-file-only"

        # mixed text + file
        r = send_files(
            client,
            owner,
            general["id"],
            [{"type": "text", "text": "смотрите файл"}],
            [("doc.bin", b"\x00\x01mixed", "application/octet-stream")],
        )
        assert r.status_code == 201, r.text
        mixed = r.json()
        assert mixed["content"][0]["text"] == "смотрите файл"
        assert len(mixed["attachments"]) == 1

        # path traversal в имени не влияет на stored path
        r = send_files(
            client,
            owner,
            general["id"],
            [],
            [("../etc/passwd", b"safe-bytes", "text/plain")],
        )
        assert r.status_code == 201, r.text
        trav = r.json()["attachments"][0]
        assert trav["original_name"] == "passwd"
        con = sqlite3.connect(TEST_DB)
        try:
            stored = con.execute(
                "SELECT stored_path FROM chat_attachments WHERE id = ?",
                (trav["id"],),
            ).fetchone()[0]
        finally:
            con.close()
        assert ".." not in stored
        assert stored.startswith("chat/")
        assert pathlib.Path(stored).name != "passwd"
        assert (UPLOADS / stored).is_file()

        # 11 файлов → TOO_MANY
        too_many = [(f"f{i}.txt", b"x", "text/plain") for i in range(11)]
        r = send_files(client, owner, general["id"], [], too_many)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "CHAT_TOO_MANY_FILES"
        assert staging_files() == []

        # лимит по фактически прочитанным байтам (малый override)
        chat_service._UPLOAD_MAX_TOTAL_BYTES_OVERRIDE = 32
        try:
            disk_before_over = set(chat_disk_files())
            r = send_files(
                client,
                owner,
                general["id"],
                [],
                [("big.bin", b"a" * 64, "application/octet-stream")],
            )
            assert r.status_code == 413, r.text
            assert r.json()["detail"]["code"] == "CHAT_FILES_TOO_LARGE"
            assert staging_files() == []
            assert set(chat_disk_files()) == disk_before_over
        finally:
            chat_service._UPLOAD_MAX_TOTAL_BYTES_OVERRIDE = None

        # rollback cleanup: падение после переноса файлов
        events_before = count_events()
        audit_before = count_audit("chat.message.created")
        disk_before_rollback = set(chat_disk_files())
        original_append_event = chat_service.append_event

        async def fail_append_event(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("forced file rollback")

        chat_service.append_event = fail_append_event
        try:
            try:
                send_files(
                    client,
                    owner,
                    general["id"],
                    [{"type": "text", "text": "rollback"}],
                    [("rb.txt", b"rollback-bytes", "text/plain")],
                )
                raise AssertionError("forced failure did not propagate")
            except RuntimeError as exc:
                assert str(exc) == "forced file rollback"
        finally:
            chat_service.append_event = original_append_event
        assert count_events() == events_before
        assert count_audit("chat.message.created") == audit_before
        assert set(chat_disk_files()) == disk_before_rollback
        assert staging_files() == []
        print("attachments upload/limits/rollback ok")

        # download access: direct attachment недоступен третьему
        r = client.post(
            "/api/chat/direct",
            headers=owner,
            json={"peer_user_id": admin_me["id"]},
        )
        assert r.status_code in (200, 201), r.text
        direct_room = r.json()
        r = send_files(
            client,
            owner,
            direct_room["id"],
            [],
            [("secret.txt", b"top-secret", "text/plain")],
        )
        assert r.status_code == 201, r.text
        secret_att = r.json()["attachments"][0]["id"]
        secret_msg = r.json()["id"]

        r = client.get(f"/api/chat/attachments/{secret_att}", headers=owner)
        assert r.status_code == 200, r.text
        assert r.content == b"top-secret"
        r = client.get(f"/api/chat/attachments/{secret_att}", headers=admin)
        assert r.status_code == 200, r.text
        r = client.get(f"/api/chat/attachments/{secret_att}", headers=admin2)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_ROOM_FORBIDDEN"
        r = client.get(f"/api/chat/attachments/{secret_att}", headers=right)
        assert r.status_code == 403, r.text
        r = client.get(f"/api/chat/attachments/{secret_att}", headers=noga)
        assert r.status_code == 403, r.text

        # soft-delete снимает metadata и файл с диска
        con = sqlite3.connect(TEST_DB)
        try:
            stored_secret = con.execute(
                "SELECT stored_path FROM chat_attachments WHERE id = ?",
                (secret_att,),
            ).fetchone()[0]
        finally:
            con.close()
        abs_secret = UPLOADS / stored_secret
        assert abs_secret.is_file()
        r = client.delete(f"/api/chat/messages/{secret_msg}", headers=owner)
        assert r.status_code == 204, r.text
        con = sqlite3.connect(TEST_DB)
        try:
            left = con.execute(
                "SELECT COUNT(*) FROM chat_attachments WHERE id = ?",
                (secret_att,),
            ).fetchone()[0]
        finally:
            con.close()
        assert left == 0
        assert not abs_secret.exists()
        r = client.get(f"/api/chat/attachments/{secret_att}", headers=owner)
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "CHAT_ATTACHMENT_NOT_FOUND"
        print("attachments download/delete ok")

        # --- Direct write + block/role ---
        r = send_text(
            client,
            owner,
            direct["id"],
            [
                {"type": "text", "text": "личный "},
                {"type": "mention", "user_id": admin_me["id"]},
            ],
        )
        assert r.status_code == 201, r.text
        direct_mention_message = r.json()
        r = client.get("/api/chat/mentions?unread_only=true", headers=admin)
        assert r.status_code == 200, r.text
        direct_mention = next(
            item
            for item in r.json()
            if item["message_id"] == direct_mention_message["id"]
        )
        assert direct_mention["room_id"] == direct["id"]
        assert direct_mention["room_title"] == owner_me["display_name"]

        # блок админа → токен больше не работает
        r = client.patch(
            f"/api/users/{admin_me['id']}",
            headers=owner,
            json={"status": "blocked"},
        )
        assert r.status_code == 200, r.text
        r = client.get("/api/chat/rooms", headers=admin)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "BLOCKED"

        # в direct с заблокированным нельзя писать
        r = send_text(
            client,
            owner,
            direct["id"],
            [{"type": "text", "text": "после блока"}],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "CHAT_DIRECT_UNAVAILABLE"

        # разблок и смена роли на noga
        r = client.patch(
            f"/api/users/{admin_me['id']}",
            headers=owner,
            json={"status": "active"},
        )
        assert r.status_code == 200, r.text
        r = client.patch(
            f"/api/users/{admin_me['id']}",
            headers=owner,
            json={"role": "noga"},
        )
        assert r.status_code == 200, r.text
        admin_as_noga = auth(client, ADMIN)
        r = client.get("/api/chat/rooms", headers=admin_as_noga)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CHAT_FORBIDDEN"

        r = send_text(
            client,
            owner,
            direct["id"],
            [{"type": "text", "text": "после смены роли"}],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "CHAT_DIRECT_UNAVAILABLE"
        print("block/role ok")

        # --- Delete user cleanup: новый direct с admin2, удаляем admin2 ---
        r = client.post(
            "/api/chat/direct",
            headers=owner,
            json={"peer_user_id": client.get("/api/me", headers=admin2).json()["id"]},
        )
        assert r.status_code == 201, r.text
        direct2 = r.json()
        peer_id = client.get("/api/me", headers=admin2).json()["id"]
        r = send_text(
            client,
            owner,
            direct2["id"],
            [{"type": "text", "text": "до удаления"}],
        )
        assert r.status_code == 201, r.text

        r = client.delete(f"/api/users/{peer_id}", headers=owner)
        assert r.status_code == 204, r.text

        r = send_text(
            client,
            owner,
            direct2["id"],
            [{"type": "text", "text": "после удаления"}],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "CHAT_DIRECT_UNAVAILABLE"
        print("delete-user chat cleanup ok")

        # --- Feature flag off → 404 ---
        os.environ["CHAT_ENABLED"] = "false"
        get_settings.cache_clear()
        r = client.get("/api/chat/rooms", headers=owner)
        assert r.status_code == 404, r.text
        # Router-level gate скрывает API даже до авторизации.
        r = client.get("/api/chat/rooms")
        assert r.status_code == 404, r.text
        r = client.get("/api/me", headers=owner)
        assert r.status_code == 200, r.text
        assert r.json()["features"]["chat"] is False
        os.environ["CHAT_ENABLED"] = "true"
        get_settings.cache_clear()
        print("CHAT_ENABLED gate ok")

        print("ALL CHAT TESTS PASSED")


if __name__ == "__main__":
    main()
