"""Smoke test for self-rename. Run from backend/: python tests/test_profile_rename.py"""

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_rename.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_rename.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
ADMIN = 333333333
NOGA = 222222222


def headers(client: TestClient, telegram_id: int) -> dict:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def main() -> None:
    with TestClient(app) as client:
        owner = headers(client, OWNER)

        for telegram_id, role in ((ADMIN, "admin"), (NOGA, "noga")):
            r = client.post(
                "/api/users",
                headers=owner,
                json={"telegram_id": telegram_id, "role": role, "display_name": "Кто-то"},
            )
            assert r.status_code == 201, r.text

        admin = headers(client, ADMIN)
        noga = headers(client, NOGA)

        me = client.get("/api/me", headers=admin).json()
        assert "profile:rename" in me["permissions"], me["permissions"]
        assert "profile:rename" not in client.get("/api/me", headers=noga).json()["permissions"]
        print("permission granted to admin, denied to noga ok")

        r = client.patch("/api/me", headers=admin, json={"display_name": "  Босс 01  "})
        assert r.status_code == 200, r.text
        assert r.json()["display_name"] == "Босс 01", r.text
        assert client.get("/api/me", headers=admin).json()["display_name"] == "Босс 01"
        print("admin renamed with cyrillic + digits ok")

        r = client.patch("/api/me", headers=owner, json={"display_name": "Chief_Ops-2"})
        assert r.status_code == 200, r.text
        assert r.json()["display_name"] == "Chief_Ops-2", r.text
        print("owner renamed with latin, dash and underscore ok")

        for bad in ("A", "x" * 33, "Иван!", "нога@2", "   ", "🙂"):
            r = client.patch("/api/me", headers=admin, json={"display_name": bad})
            assert r.status_code == 400, (bad, r.text)
            assert r.json()["detail"]["code"] == "BAD_REQUEST", r.text
        print("invalid nicks rejected ok")

        r = client.patch("/api/me", headers=noga, json={"display_name": "Нога"})
        assert r.status_code == 403, r.text
        print("noga cannot rename itself -> 403 ok")

        # Роль и статус через этот эндпоинт не проезжают.
        r = client.patch("/api/me", headers=admin, json={"display_name": "Босс 02", "role": "owner"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin", r.text
        print("role in body ignored ok")

    print("PROFILE RENAME TESTS OK")


if __name__ == "__main__":
    main()
