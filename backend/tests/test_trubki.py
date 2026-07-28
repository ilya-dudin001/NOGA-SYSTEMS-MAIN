"""Smoke test for трубки (заказы). Run from backend/: python tests/test_trubki.py"""

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_trubki.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_trubki.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
ADMIN_USER = 333333333
NOGA_USER = 222222222


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main() -> None:
    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}

        for tid, role in ((ADMIN_USER, "admin"), (NOGA_USER, "noga")):
            r = client.post(
                "/api/users",
                headers=owner,
                json={"telegram_id": tid, "role": role, "display_name": role},
            )
            assert r.status_code == 201, r.text
        admin = {"Authorization": "Bearer " + token(client, ADMIN_USER)}
        noga_user = {"Authorization": "Bearer " + token(client, NOGA_USER)}

        r = client.post(
            "/api/razgruzy", headers=owner, json={"name": "Альфа", "commission_percent": 3}
        )
        assert r.status_code == 201, r.text
        alfa = r.json()

        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "Тула", "razgruz_ids": [alfa["id"]]},
        )
        assert r.status_code == 201, r.text
        tula = r.json()

        # Ногу заводит админ: «чья нога» в трубке должна показать именно его.
        r = client.post(
            "/api/nogas", headers=admin, json={"name": "Пётр", "city_id": tula["id"]}
        )
        assert r.status_code == 201, r.text
        petr = r.json()

        # --- Создание ---
        payload = {
            "city_id": tula["id"],
            "noga_id": petr["id"],
            "razgruz_id": alfa["id"],
            "amount": 250000,
            "amount_currency": "RUB",
            "customer_name": "Иванов Иван Иванович",
            "customer_address": "Тула, Ленина 1, кв. 5",
            "delivery": "taxi",
        }
        r = client.post("/api/trubki", headers=owner, json=payload)
        assert r.status_code == 201, r.text
        trubka = r.json()
        assert trubka["status"] == "zacep", trubka
        assert trubka["city_name"] == "Тула"
        assert trubka["noga_name"] == "Пётр"
        assert trubka["noga_owner_name"] == "admin", trubka
        assert trubka["razgruz_name"] == "Альфа"
        assert trubka["delivery"] == "taxi"
        assert trubka["can_manage"] is True
        print("trubka created ok")

        # --- Чтение: видят все, включая роль noga ---
        r = client.get("/api/trubki", headers=noga_user)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1
        assert r.json()[0]["can_manage"] is False, r.json()[0]
        print("noga role reads trubki, cannot manage ok")

        # --- Роль noga не заводит и не правит ---
        r = client.post("/api/trubki", headers=noga_user, json=payload)
        assert r.status_code == 403, r.text
        r = client.patch(
            f"/api/trubki/{trubka['id']}", headers=noga_user, json={"status": "srez"}
        )
        assert r.status_code == 403, r.text
        print("noga role write -> 403 ok")

        # --- Правка статуса и сброс разгруза ---
        r = client.patch(
            f"/api/trubki/{trubka['id']}",
            headers=admin,
            json={"status": "razgruzheno", "amount": 300000, "razgruz_id": None},
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["status"] == "razgruzheno"
        assert updated["amount"] == 300000
        assert updated["razgruz_id"] is None, updated
        print("trubka updated ok")

        # --- Фильтры ---
        r = client.get("/api/trubki?status=zacep", headers=owner)
        assert r.status_code == 200 and r.json() == [], r.text
        r = client.get(f"/api/trubki?city_id={tula['id']}", headers=owner)
        assert len(r.json()) == 1, r.text
        print("filters ok")

        # --- Сводка дашборда ---
        r = client.get("/api/dashboard/summary", headers=owner)
        assert r.status_code == 200, r.text
        summary = r.json()["trubki"]
        assert summary["total"] == 1 and summary["razgruzheno"] == 1, summary
        print("dashboard summary ok")

        # --- Ссылки не дают снести справочники ---
        r = client.delete(f"/api/nogas/{petr['id']}", headers=admin)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "NOGA_HAS_TRUBKI", r.text
        r = client.delete(f"/api/cities/{tula['id']}?detach_nogas=true", headers=owner)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "CITY_HAS_TRUBKI", r.text
        print("delete guards ok")

        # Разгруз сняли с трубки выше — теперь он удаляется как обычно.
        r = client.post(
            "/api/trubki",
            headers=owner,
            json=dict(payload, razgruz_id=alfa["id"], status="vedut"),
        )
        assert r.status_code == 201, r.text
        second = r.json()
        r = client.delete(f"/api/razgruzy/{alfa['id']}?detach_cities=true", headers=owner)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "RAZGRUZ_HAS_TRUBKI", r.text
        print("razgruz guard ok")

        # --- Удаление трубки ---
        r = client.delete(f"/api/trubki/{second['id']}", headers=admin)
        assert r.status_code == 204, r.text
        r = client.get(f"/api/trubki/{second['id']}", headers=owner)
        assert r.status_code == 404, r.text
        print("trubka deleted ok")

        # --- Неизвестные ссылки ---
        r = client.post("/api/trubki", headers=owner, json=dict(payload, city_id=9999))
        assert r.status_code == 404, r.text
        r = client.post("/api/trubki", headers=owner, json=dict(payload, noga_id=9999))
        assert r.status_code == 404, r.text
        print("unknown refs -> 404 ok")

    print("\nALL TRUBKI TESTS PASSED")


if __name__ == "__main__":
    main()
