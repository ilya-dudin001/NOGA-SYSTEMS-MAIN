"""Smoke test for user deletion. Run from backend/: python tests/test_delete_user.py"""

import os
import pathlib
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
        r = client.delete(
            f"/api/users/{admin_id}", headers={"Authorization": "Bearer " + noga_token}
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "FORBIDDEN"
        print("noga cannot delete -> 403 ok")

        me = client.get("/api/me", headers=owner_headers).json()
        r = client.delete(f"/api/users/{me['id']}", headers=owner_headers)
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

        r = client.delete(f"/api/users/{me['id']}", headers=owner2_headers)
        assert r.status_code == 401, r.text
        print("token of deleted owner revoked ok")

        r = client.delete(f"/api/users/{noga_id}", headers=owner_headers)
        assert r.status_code == 204, r.text
        r = client.get("/api/me", headers={"Authorization": "Bearer " + noga_token})
        assert r.status_code == 401, r.text
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
