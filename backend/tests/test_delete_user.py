"""Smoke test for user deletion. Run from backend/: python tests/test_delete_user.py"""

import os
import pathlib
import sqlite3
import sys

TEST_DB = pathlib.Path("data/test_delete.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_delete.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
NOGA = 222222222
ADMIN = 333333333
OWNER2 = 444444444


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main() -> None:
    with TestClient(app) as client:
        owner_headers = {"Authorization": "Bearer " + token(client, OWNER)}
        owner_me = client.get("/api/me", headers=owner_headers).json()
        assert owner_me["features"]["chat"] is True
        assert "chat:delete_any" in owner_me["permissions"]

        r = client.post(
            "/api/users",
            headers=owner_headers,
            json={"telegram_id": NOGA, "role": "noga", "display_name": "Nora"},
        )
        assert r.status_code == 201, r.text
        noga_id = r.json()["id"]

        r = client.post(
            "/api/users",
            headers=owner_headers,
            json={"telegram_id": ADMIN, "role": "admin", "display_name": "Admin"},
        )
        assert r.status_code == 201, r.text
        admin_id = r.json()["id"]

        noga_token = token(client, NOGA)
        noga_me = client.get(
            "/api/me", headers={"Authorization": "Bearer " + noga_token}
        ).json()
        assert noga_me["features"]["chat"] is False
        assert not any(p.startswith("chat:") for p in noga_me["permissions"])
        r = client.delete(
            f"/api/users/{admin_id}", headers={"Authorization": "Bearer " + noga_token}
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "FORBIDDEN"
        print("noga cannot delete -> 403 ok")

        r = client.delete(f"/api/users/{owner_me['id']}", headers=owner_headers)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["message"] == "Нельзя удалить себя"
        print("self delete blocked ok")

        r = client.post(
            "/api/users",
            headers=owner_headers,
            json={"telegram_id": OWNER2, "role": "owner", "display_name": "Owner2"},
        )
        assert r.status_code == 201, r.text
        owner2_id = r.json()["id"]
        owner2_headers = {"Authorization": "Bearer " + token(client, OWNER2)}

        # Second owner deletes the bootstrap owner is allowed (two owners exist),
        # but the last remaining owner must be protected.
        r = client.delete(f"/api/users/{owner2_id}", headers=owner_headers)
        assert r.status_code == 204, r.text
        print("owner deletes another owner ok")

        r = client.delete(f"/api/users/{owner_me['id']}", headers=owner2_headers)
        assert r.status_code == 401, r.text
        print("token of deleted owner revoked ok")

        with sqlite3.connect(TEST_DB) as db:
            assert db.execute(
                "SELECT COUNT(*) FROM chat_rooms WHERE kind = 'system'"
            ).fetchone()[0] == 2
            direct_key = ":".join(map(str, sorted((owner_me["id"], noga_id))))
            cursor = db.execute(
                """
                INSERT INTO chat_rooms
                    (kind, direct_key, is_active, sort_order, created_at, updated_at)
                VALUES ('direct', ?, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (direct_key,),
            )
            room_id = cursor.lastrowid
            db.executemany(
                """
                INSERT INTO chat_room_members (room_id, user_id, joined_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                ((room_id, owner_me["id"]), (room_id, noga_id)),
            )
            cursor = db.execute(
                """
                INSERT INTO chat_messages
                    (room_id, author_id, author_name, body, content, created_at)
                VALUES (?, ?, 'Nora', 'hello', '[{"type":"text","text":"hello"}]',
                        CURRENT_TIMESTAMP)
                """,
                (room_id, noga_id),
            )
            message_id = cursor.lastrowid
            db.execute(
                """
                INSERT INTO chat_attachments
                    (message_id, stored_path, original_name, content_type,
                     size_bytes, uploaded_by_id, created_at)
                VALUES (?, 'chat/test/file', 'file.bin', 'application/octet-stream',
                        1, ?, CURRENT_TIMESTAMP)
                """,
                (message_id, noga_id),
            )
            db.execute(
                """
                INSERT INTO chat_mentions
                    (message_id, user_id, user_name, telegram_status,
                     telegram_attempts, created_at)
                VALUES (?, ?, 'Nora', 'pending', 0, CURRENT_TIMESTAMP)
                """,
                (message_id, noga_id),
            )
            db.execute(
                """
                INSERT INTO chat_reads (room_id, user_id, last_read_message_id, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (room_id, noga_id, message_id),
            )
            db.execute(
                """
                INSERT INTO chat_events (room_id, target_user_id, type, payload, created_at)
                VALUES (?, ?, 'mention.created', '{}', CURRENT_TIMESTAMP)
                """,
                (room_id, noga_id),
            )
            db.execute(
                """
                INSERT INTO chat_events (room_id, target_user_id, type, payload, created_at)
                VALUES (?, NULL, 'message.created', '{}', CURRENT_TIMESTAMP)
                """,
                (room_id,),
            )

        r = client.delete(f"/api/users/{noga_id}", headers=owner_headers)
        assert r.status_code == 204, r.text
        r = client.get("/api/me", headers={"Authorization": "Bearer " + noga_token})
        assert r.status_code == 401, r.text
        with sqlite3.connect(TEST_DB) as db:
            message = db.execute(
                "SELECT author_id, author_name FROM chat_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            assert message == (None, "Nora"), message
            assert db.execute(
                "SELECT uploaded_by_id FROM chat_attachments WHERE message_id = ?",
                (message_id,),
            ).fetchone()[0] is None
            mention = db.execute(
                "SELECT user_id, telegram_status FROM chat_mentions WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            assert mention == (None, "cancelled"), mention
            assert db.execute(
                "SELECT COUNT(*) FROM chat_reads WHERE user_id = ?", (noga_id,)
            ).fetchone()[0] == 0
            assert db.execute(
                "SELECT COUNT(*) FROM chat_room_members WHERE user_id = ?", (noga_id,)
            ).fetchone()[0] == 0
            assert db.execute(
                "SELECT COUNT(*) FROM chat_events WHERE target_user_id = ?", (noga_id,)
            ).fetchone()[0] == 0
            assert db.execute(
                "SELECT COUNT(*) FROM chat_events WHERE room_id = ? AND target_user_id IS NULL",
                (room_id,),
            ).fetchone()[0] == 1
        print("deleted user token revoked ok")

        r = client.delete("/api/users/9999", headers=owner_headers)
        assert r.status_code == 404, r.text
        print("missing user -> 404 ok")

        users = client.get("/api/users", headers=owner_headers).json()
        remaining = {u["telegram_id"] for u in users}
        assert remaining == {OWNER, ADMIN}, remaining
        print("remaining users:", sorted(remaining))

    print("DELETE TESTS OK")


if __name__ == "__main__":
    main()
