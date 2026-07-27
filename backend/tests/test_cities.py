"""Smoke test for управление городами и разгрузами. Run from backend/: python tests/test_cities.py"""

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_cities.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_cities.db"
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

        # --- Разгрузы ---
        r = client.post(
            "/api/razgruzy",
            headers=owner,
            json={"name": "Альфа", "commission_percent": 3.5, "contact": "@alfa"},
        )
        assert r.status_code == 201, r.text
        alfa = r.json()
        assert alfa["commission_percent"] == 3.5
        assert alfa["created_by_name"] == "Owner", alfa
        assert alfa["completed_orders"] == 0
        print("razgruz created ok")

        r = client.post(
            "/api/razgruzy", headers=owner, json={"name": "бета", "commission_percent": 2}
        )
        beta = r.json()
        assert r.status_code == 201, r.text

        # Дубликат названия без учёта регистра
        r = client.post("/api/razgruzy", headers=owner, json={"name": "АЛЬФА"})
        assert r.status_code == 409, r.text
        print("duplicate razgruz name -> 409 ok")

        # --- Города ---
        r = client.post(
            "/api/cities",
            headers=owner,
            json={
                "name": "Тула",
                "min_amount": 200000,
                "min_amount_currency": "RUB",
                "razgruz_ids": [alfa["id"], beta["id"]],
            },
        )
        assert r.status_code == 201, r.text
        tula = r.json()
        assert tula["status"] == "working"
        assert tula["min_amount"] == 200000 and tula["min_amount_currency"] == "RUB"
        assert sorted(x["name"] for x in tula["razgruzy"]) == ["Альфа", "бета"]
        assert tula["razgruzy"][0]["commission_percent"] in (2.0, 3.5)
        assert tula["nogas"] == [] and tula["recent_orders"] == []
        assert tula["created_by_name"] == "Owner"
        print("city created with razgruzy ok")

        # Сумма без валюты запрещена
        r = client.post(
            "/api/cities", headers=owner, json={"name": "Казань", "min_amount": 500}
        )
        assert r.status_code == 400, r.text
        print("amount without currency -> 400 ok")

        # Несуществующий разгруз
        r = client.post(
            "/api/cities", headers=owner, json={"name": "Казань", "razgruz_ids": [999]}
        )
        assert r.status_code == 404, r.text

        # Дубликат города без учёта регистра
        r = client.post("/api/cities", headers=owner, json={"name": "тула"})
        assert r.status_code == 409, r.text
        print("duplicate city -> 409 ok")

        # Валюта из списка СНГ
        r = client.post(
            "/api/cities",
            headers=owner,
            json={
                "name": "Ташкент",
                "min_amount": 25000000,
                "min_amount_currency": "UZS",
                "status": "paused",
            },
        )
        assert r.status_code == 201, r.text
        tashkent = r.json()
        assert tashkent["min_amount_currency"] == "UZS"
        assert tashkent["status"] == "paused"
        print("uzs city with paused status ok")

        # Неизвестная валюта отбивается валидацией
        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "Рига", "min_amount": 100, "min_amount_currency": "EUR"},
        )
        assert r.status_code == 422, r.text

        # --- Ноги подтягиваются в детали города ---
        r = client.post(
            "/api/nogas", headers=owner, json={"name": "Иван", "city_id": tula["id"]}
        )
        assert r.status_code == 201, r.text
        detail = client.get(f"/api/cities/{tula['id']}", headers=owner).json()
        assert [n["name"] for n in detail["nogas"]] == ["Иван"]
        assert detail["nogas"][0]["created_by_name"] == "Owner", detail["nogas"]
        assert detail["nogas_count"] == 1
        print("city detail pulls nogas with author ok")

        # --- Статусы ---
        for value in ("paused", "stopped", "working"):
            r = client.patch(
                f"/api/cities/{tula['id']}", headers=owner, json={"status": value}
            )
            assert r.status_code == 200 and r.json()["status"] == value, r.text
        r = client.patch(f"/api/cities/{tula['id']}", headers=owner, json={"status": "x"})
        assert r.status_code == 422, r.text
        print("statuses working/paused/stopped ok")

        # --- Редактирование ---
        r = client.patch(
            f"/api/cities/{tula['id']}",
            headers=owner,
            json={"min_amount": 300000, "min_amount_currency": "RUB"},
        )
        assert r.status_code == 200 and r.json()["min_amount"] == 300000, r.text

        # Сброс суммы: явные null по обоим полям
        r = client.patch(
            f"/api/cities/{tula['id']}",
            headers=owner,
            json={"min_amount": None, "min_amount_currency": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["min_amount"] is None and r.json()["min_amount_currency"] is None

        # Сброс только суммы, без валюты — ошибка
        r = client.patch(
            f"/api/cities/{tula['id']}",
            headers=owner,
            json={"min_amount": 100, "min_amount_currency": "RUB"},
        )
        assert r.status_code == 200
        r = client.patch(
            f"/api/cities/{tula['id']}", headers=owner, json={"min_amount": None}
        )
        assert r.status_code == 400, r.text
        print("min amount set / clear / half-clear ok")

        # Переименование в занятое имя -> 409 без 500, город не меняется
        r = client.patch(
            f"/api/cities/{tula['id']}", headers=owner, json={"name": "ташкент"}
        )
        assert r.status_code == 409, r.text
        assert client.get(f"/api/cities/{tula['id']}", headers=owner).json()["name"] == "Тула"
        print("rename to existing -> 409, unchanged ok")

        # Пересборка списка разгрузов
        r = client.patch(
            f"/api/cities/{tula['id']}", headers=owner, json={"razgruz_ids": [beta["id"]]}
        )
        assert r.status_code == 200, r.text
        assert [x["name"] for x in r.json()["razgruzy"]] == ["бета"], r.json()
        r = client.patch(
            f"/api/cities/{tula['id']}", headers=owner, json={"razgruz_ids": []}
        )
        assert r.json()["razgruzy"] == [], r.text
        print("razgruz links replaced ok")

        # cities_count у разгруза считается
        r = client.patch(
            f"/api/cities/{tashkent['id']}",
            headers=owner,
            json={"razgruz_ids": [alfa["id"]]},
        )
        assert r.status_code == 200, r.text
        listing = client.get("/api/razgruzy", headers=owner).json()
        alfa_row = [x for x in listing if x["id"] == alfa["id"]][0]
        assert alfa_row["cities_count"] == 1, listing
        print("razgruz cities_count ok")

        # Привязанный разгруз просто так не удалить: сначала предупреждение с городами
        r = client.delete(f"/api/razgruzy/{alfa['id']}", headers=owner)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "RAZGRUZ_HAS_CITIES", r.text
        assert r.json()["detail"]["cities"] == ["Ташкент"], r.text
        assert client.delete(f"/api/razgruzy/{beta['id']}", headers=owner).status_code == 204
        print("linked razgruz -> 409 with city names, free razgruz deleted ok")

        # --- Удаление города ---
        assert client.delete(f"/api/cities/{tula['id']}", headers=owner).status_code == 409
        nogas = client.get(f"/api/nogas?city_id={tula['id']}", headers=owner).json()
        assert client.delete(f"/api/nogas/{nogas[0]['id']}", headers=owner).status_code == 204
        assert client.delete(f"/api/cities/{tula['id']}", headers=owner).status_code == 204
        assert client.get(f"/api/cities/{tula['id']}", headers=owner).status_code == 404
        print("city delete blocked by nogas, then ok")

        # С флагом разгруз отвязывается от городов и удаляется, города остаются
        r = client.delete(f"/api/razgruzy/{alfa['id']}?detach_cities=true", headers=owner)
        assert r.status_code == 204, r.text
        tashkent_after = client.get(f"/api/cities/{tashkent['id']}", headers=owner)
        assert tashkent_after.status_code == 200 and tashkent_after.json()["razgruzy"] == []
        print("detach_cities unlinks razgruz and keeps cities ok")

        # Удаление города снимает связи с разгрузами
        r = client.post("/api/razgruzy", headers=owner, json={"name": "Дельта"})
        delta_id = r.json()["id"]
        client.patch(
            f"/api/cities/{tashkent['id']}", headers=owner, json={"razgruz_ids": [delta_id]}
        )
        assert client.delete(f"/api/cities/{tashkent['id']}", headers=owner).status_code == 204
        listing = client.get("/api/razgruzy", headers=owner).json()
        assert [x for x in listing if x["id"] == delta_id][0]["cities_count"] == 0
        assert client.delete(f"/api/razgruzy/{delta_id}", headers=owner).status_code == 204
        print("city delete unlinks razgruzy ok")

        # --- Права ---
        noga_h = {"Authorization": "Bearer " + token(client, NOGA_USER)}
        assert client.get("/api/cities", headers=noga_h).status_code == 200
        assert client.post("/api/cities", headers=noga_h, json={"name": "X"}).status_code == 403
        assert client.get("/api/razgruzy", headers=noga_h).status_code == 403

        # Роль noga имеет cities:read ради форм операций, но комиссии разгрузов
        # и состав ног ей видеть не положено
        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "Витрина", "razgruz_ids": []},
        )
        vitrina_id = r.json()["id"]
        r = client.post("/api/razgruzy", headers=owner, json={"name": "Гамма"})
        gamma_id = r.json()["id"]
        client.patch(
            f"/api/cities/{vitrina_id}", headers=owner, json={"razgruz_ids": [gamma_id]}
        )
        client.post("/api/nogas", headers=owner, json={"name": "Пётр", "city_id": vitrina_id})

        as_owner = client.get(f"/api/cities/{vitrina_id}", headers=owner).json()
        assert len(as_owner["razgruzy"]) == 1 and len(as_owner["nogas"]) == 1

        as_noga = client.get(f"/api/cities/{vitrina_id}", headers=noga_h).json()
        assert as_noga["razgruzy"] == [] and as_noga["nogas"] == [], as_noga
        assert as_noga["nogas_count"] == 1, as_noga
        listing = client.get("/api/cities", headers=noga_h).json()
        assert all(c["razgruzy"] == [] for c in listing), listing
        print("noga sees cities without razgruzy/nogas details ok")

        # Убираем витрину, чтобы сводка ниже считалась на чистых данных
        nogas = client.get(f"/api/nogas?city_id={vitrina_id}", headers=owner).json()
        client.delete(f"/api/nogas/{nogas[0]['id']}", headers=owner)
        assert client.delete(f"/api/cities/{vitrina_id}", headers=owner).status_code == 204
        assert client.delete(f"/api/razgruzy/{gamma_id}", headers=owner).status_code == 204

        admin_h = {"Authorization": "Bearer " + token(client, ADMIN_USER)}
        assert client.get("/api/cities", headers=admin_h).status_code == 200
        assert client.get("/api/razgruzy", headers=admin_h).status_code == 200
        # Админ ведёт свой участок: заводит и город, и разгруз
        r = client.post("/api/cities", headers=admin_h, json={"name": "Админовск"})
        assert r.status_code == 201, r.text
        assert r.json()["can_manage"] is True, r.text
        admin_city = r.json()["id"]
        r = client.post("/api/razgruzy", headers=admin_h, json={"name": "Эпсилон"})
        assert r.status_code == 201, r.text
        assert r.json()["can_manage"] is True and r.json()["created_by_me"] is True, r.text
        admin_razgruz = r.json()["id"]
        # Чужой разгруз админу виден, но не правится
        mine_for_owner = [
            x for x in client.get("/api/razgruzy", headers=owner).json()
            if x["id"] == admin_razgruz
        ][0]
        assert mine_for_owner["can_manage"] is True, "owner правит любые разгрузы"
        assert mine_for_owner["created_by_me"] is False, mine_for_owner
        assert client.delete(f"/api/cities/{admin_city}", headers=admin_h).status_code == 204
        assert client.delete(f"/api/razgruzy/{admin_razgruz}", headers=admin_h).status_code == 204
        print("permissions ok")

        # --- Сводка на дашборде ---
        for name, city_status in (("Тула", "working"), ("Самара", "paused"), ("Омск", "stopped")):
            r = client.post(
                "/api/cities", headers=owner, json={"name": name, "status": city_status}
            )
            assert r.status_code == 201, r.text
        summary = client.get("/api/dashboard/summary", headers=owner).json()
        assert summary["cities"] == {
            "total": 3,
            "working": 1,
            "paused": 1,
            "stopped": 1,
            "nogas": 0,
            "razgruzy": 0,
        }, summary
        noga_summary = client.get("/api/dashboard/summary", headers=noga_h).json()
        assert noga_summary["scope"] == "own"
        print("dashboard cities summary ok")

        me = client.get("/api/me", headers=owner).json()
        assert "razgruz:manage" in me["permissions"]

    print("CITIES TESTS OK")


if __name__ == "__main__":
    main()
