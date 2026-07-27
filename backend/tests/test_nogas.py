"""Smoke test for нога management. Run from backend/: python tests/test_nogas.py"""

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_nogas.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_nogas.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
NOGA_USER = 222222222
ADMIN_USER = 333333333


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main() -> None:
    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}

        for tid, role in ((NOGA_USER, "noga"), (ADMIN_USER, "admin")):
            r = client.post(
                "/api/users",
                headers=owner,
                json={"telegram_id": tid, "role": role, "display_name": role},
            )
            assert r.status_code == 201, r.text

        # Нога создаётся вместе с новым городом одним запросом
        r = client.post(
            "/api/nogas",
            headers=owner,
            json={"name": "Иван", "city_name": "Тула", "is_test": False},
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["city_name"] == "Тула"
        assert created["is_test"] is False
        assert created["is_active"] is True
        tula_id = created["city_id"]
        ivan_id = created["id"]
        print("created noga with new city ok")

        # Город переиспользуется, регистр не создаёт дубликат
        r = client.post(
            "/api/nogas",
            headers=owner,
            json={"name": "Максим", "city_name": "тула", "is_test": True},
        )
        assert r.status_code == 201, r.text
        assert r.json()["city_id"] == tula_id, "город продублировался"
        assert r.json()["is_test"] is True
        print("city reused case-insensitively ok")

        cities = client.get("/api/cities", headers=owner).json()
        assert len(cities) == 1, cities
        print("cities:", [c["name"] for c in cities])

        # Дубль имени в том же городе запрещён
        r = client.post(
            "/api/nogas", headers=owner, json={"name": "Иван", "city_id": tula_id}
        )
        assert r.status_code == 409, r.text
        print("duplicate name in city -> 409 ok")

        # То же имя в другом городе разрешено
        r = client.post(
            "/api/nogas", headers=owner, json={"name": "Иван", "city_name": "Самара"}
        )
        assert r.status_code == 201, r.text
        print("same name in another city ok")

        # Город обязателен
        r = client.post("/api/nogas", headers=owner, json={"name": "Безгорода"})
        assert r.status_code == 400, r.text
        print("city required -> 400 ok")

        # Переключение теста и активности
        r = client.patch(f"/api/nogas/{ivan_id}", headers=owner, json={"is_test": True})
        assert r.status_code == 200 and r.json()["is_test"] is True, r.text
        r = client.patch(f"/api/nogas/{ivan_id}", headers=owner, json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False, r.text
        print("toggle is_test / is_active ok")

        # Перенос, который создал бы дубликат, отклоняется без 500
        samara_id = [
            c["id"] for c in client.get("/api/cities", headers=owner).json() if c["name"] == "Самара"
        ][0]
        r = client.patch(f"/api/nogas/{ivan_id}", headers=owner, json={"city_id": samara_id})
        assert r.status_code == 409, r.text
        r = client.get("/api/nogas", headers=owner).json()
        assert [n for n in r if n["id"] == ivan_id][0]["city_name"] == "Тула"
        print("move that would duplicate -> 409, city unchanged ok")

        # Корректный перенос отдаёт свежее название города
        r = client.post("/api/nogas", headers=owner, json={"name": "Пётр", "city_id": tula_id})
        petr_id = r.json()["id"]
        r = client.patch(f"/api/nogas/{petr_id}", headers=owner, json={"city_id": samara_id})
        assert r.status_code == 200, r.text
        assert r.json()["city_name"] == "Самара", r.text
        print("move to another city ok")

        # Несуществующий город
        r = client.patch(f"/api/nogas/{petr_id}", headers=owner, json={"city_id": 9999})
        assert r.status_code == 404, r.text
        print("unknown city -> 404 ok")

        # Фильтры
        r = client.get("/api/nogas?include_test=false", headers=owner)
        assert r.status_code == 200
        assert all(not n["is_test"] for n in r.json())
        r = client.get("/api/nogas?only_active=true", headers=owner)
        assert all(n["is_active"] for n in r.json())
        print("filters ok")

        # Права: нога не видит список, админ видит но не меняет
        noga_h = {"Authorization": "Bearer " + token(client, NOGA_USER)}
        assert client.get("/api/nogas", headers=noga_h).status_code == 403
        assert client.get("/api/cities", headers=noga_h).status_code == 200
        print("noga: nogas 403, cities 200 ok")

        admin_h = {"Authorization": "Bearer " + token(client, ADMIN_USER)}
        assert client.get("/api/nogas", headers=admin_h).status_code == 200
        r = client.post("/api/nogas", headers=admin_h, json={"name": "X", "city_id": tula_id})
        assert r.status_code == 403, r.text
        assert client.delete(f"/api/nogas/{ivan_id}", headers=admin_h).status_code == 403
        print("admin: read ok, write 403 ok")

        # Удаление
        assert client.delete(f"/api/nogas/{ivan_id}", headers=owner).status_code == 204
        assert client.delete(f"/api/nogas/{ivan_id}", headers=owner).status_code == 404
        print("delete ok, second delete -> 404 ok")

        final = client.get("/api/nogas", headers=owner).json()
        print("remaining nogas:", [(n["name"], n["city_name"], n["is_test"]) for n in final])

        me = client.get("/api/me", headers=owner).json()
        assert "nogas:manage" in me["permissions"]
        print("owner permissions include nogas:manage ok")

    print("NOGAS TESTS OK")


if __name__ == "__main__":
    main()
