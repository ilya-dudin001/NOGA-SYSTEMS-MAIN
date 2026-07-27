"""Участок администратора: свои ноги и города, общий список городов в работе.

Запуск из backend/: python tests/test_admin_scope.py
"""

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_admin_scope.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_admin_scope.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
ADMIN_A = 222222222
ADMIN_B = 333333333


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def names(items) -> list[str]:
    return sorted(item["name"] for item in items)


def main() -> None:
    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}
        for tid, name in ((ADMIN_A, "Админ А"), (ADMIN_B, "Админ Б")):
            r = client.post(
                "/api/users",
                headers=owner,
                json={"telegram_id": tid, "role": "admin", "display_name": name},
            )
            assert r.status_code == 201, r.text
        a = {"Authorization": "Bearer " + token(client, ADMIN_A)}
        b = {"Authorization": "Bearer " + token(client, ADMIN_B)}

        # ---------- свои города ----------

        r = client.post("/api/cities", headers=a, json={"name": "Тула"})
        assert r.status_code == 201, r.text
        tula = r.json()["id"]
        r = client.post("/api/cities", headers=b, json={"name": "Самара", "status": "paused"})
        samara = r.json()["id"]
        r = client.post("/api/cities", headers=owner, json={"name": "Омск"})
        omsk = r.json()["id"]

        assert names(client.get("/api/cities", headers=a).json()) == ["Тула"]
        assert names(client.get("/api/cities", headers=b).json()) == ["Самара"]
        assert names(client.get("/api/cities", headers=owner).json()) == [
            "Омск",
            "Самара",
            "Тула",
        ], "owner ведёт все города"
        print("own cities scope ok")

        # ---------- общая витрина: города в работе ----------

        shared = client.get("/api/cities?scope=working", headers=a).json()
        assert names(shared) == ["Омск", "Тула"], shared
        assert [c["can_manage"] for c in shared if c["name"] == "Омск"] == [False]
        assert [c["can_manage"] for c in shared if c["name"] == "Тула"] == [True]
        print("shared working cities visible to everyone ok")

        # Чужой город можно открыть, но не править
        assert client.get(f"/api/cities/{omsk}", headers=a).status_code == 200
        assert client.get(f"/api/cities/{omsk}", headers=a).json()["can_manage"] is False
        assert (
            client.patch(f"/api/cities/{omsk}", headers=a, json={"name": "Омск-2"}).status_code
            == 403
        )
        assert client.delete(f"/api/cities/{omsk}", headers=a).status_code == 403
        print("foreign city read-only ok")

        # ---------- ноги разных админов в одном городе ----------

        r = client.post("/api/nogas", headers=a, json={"name": "Иван", "city_id": tula})
        assert r.status_code == 201, r.text
        ivan = r.json()["id"]
        # Админ Б прикрепляет свою ногу к чужому городу — так и задумано
        r = client.post("/api/nogas", headers=b, json={"name": "Пётр", "city_id": tula})
        assert r.status_code == 201, r.text
        petr = r.json()["id"]

        assert names(client.get("/api/nogas", headers=a).json()) == ["Иван"]
        assert names(client.get("/api/nogas", headers=b).json()) == ["Пётр"]
        assert client.get("/api/nogas?scope=all", headers=a).status_code == 403
        assert names(client.get("/api/nogas", headers=owner).json()) == ["Иван", "Пётр"]
        print("own nogas scope ok")

        # В деталях города видны обе ноги с авторами, счётчик — общий
        detail = client.get(f"/api/cities/{tula}", headers=a).json()
        assert detail["nogas_count"] == 2, detail
        assert names(detail["nogas"]) == ["Иван", "Пётр"], detail["nogas"]
        by_name = {n["name"]: n for n in detail["nogas"]}
        assert by_name["Пётр"]["created_by_name"] == "Админ Б"
        assert by_name["Пётр"]["can_manage"] is False, "чужую ногу админ А не правит"
        assert by_name["Иван"]["can_manage"] is True
        print("city details sum nogas of all admins ok")

        # Тот же город в списке админа Б: он там из-за своей ноги
        assert names(client.get("/api/cities", headers=b).json()) == ["Самара", "Тула"]
        assert [
            c["can_manage"] for c in client.get("/api/cities", headers=b).json()
            if c["name"] == "Тула"
        ] == [False]
        print("city with my noga appears in my list, still read-only ok")

        # Сводка на дашборде считает всё, без разбивки по авторам
        summary = client.get("/api/dashboard/summary", headers=a).json()["cities"]
        assert summary["total"] == 3 and summary["nogas"] == 2, summary
        print("dashboard sums nogas of all admins ok")

        # ---------- чужие ноги в форме своего города ----------

        r = client.patch(f"/api/cities/{tula}", headers=a, json={"noga_ids": [ivan]})
        assert r.status_code == 200, r.text
        assert names(r.json()["nogas"]) == ["Иван", "Пётр"], "чужая нога осталась в городе"

        r = client.patch(f"/api/cities/{tula}", headers=a, json={"noga_ids": [ivan, petr]})
        assert r.status_code == 403, r.text
        assert "Пётр" in r.json()["detail"]["message"], r.text
        print("foreign noga cannot be moved from city form ok")

        # Тёзка чужой ноги в тот же город не влезет
        r = client.post("/api/nogas", headers=a, json={"name": "Пётр"})
        assert r.status_code == 201, r.text
        petr_clone = r.json()["id"]
        r = client.patch(f"/api/cities/{tula}", headers=a, json={"noga_ids": [ivan, petr_clone]})
        assert r.status_code == 409, r.text
        assert client.delete(f"/api/nogas/{petr_clone}", headers=a).status_code == 204
        print("name clash with foreign noga -> 409 ok")

        # Снять свою ногу с города админ А может, чужая остаётся
        r = client.patch(f"/api/cities/{tula}", headers=a, json={"noga_ids": []})
        assert r.status_code == 200, r.text
        assert names(r.json()["nogas"]) == ["Пётр"], r.json()["nogas"]
        assert client.get(f"/api/nogas/{ivan}", headers=a).json()["city_id"] is None
        print("detaching own noga keeps foreign one ok")

        # ---------- удаление своего города с чужой ногой ----------

        r = client.delete(f"/api/cities/{tula}", headers=a)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["nogas"] == ["Пётр"], r.text
        r = client.delete(f"/api/cities/{tula}?detach_nogas=true", headers=a)
        assert r.status_code == 204, r.text
        petr_after = client.get(f"/api/nogas/{petr}", headers=b).json()
        assert petr_after["city_id"] is None and petr_after["last_city_name"] == "Тула"
        print("deleting own city detaches foreign noga, noga survives ok")

        # ---------- личные данные чужой ноги ----------

        r = client.patch(f"/api/nogas/{petr}", headers=b, json={"phones": ["+7 900 000-00-00"]})
        assert r.status_code == 200, r.text
        detail = client.get(f"/api/nogas/{petr}", headers=a).json()
        assert detail["has_personal_access"] is True and detail["phones"], detail
        assert detail["can_manage"] is False, detail
        assert (
            client.patch(f"/api/nogas/{petr}", headers=a, json={"phones": []}).status_code == 403
        )
        print("foreign noga: personal data readable, edits blocked ok")

        # Роль «нога» витрину видит, но состав — нет
        assert client.get("/api/cities?scope=working", headers=b).status_code == 200
        assert client.get(f"/api/cities/{samara}", headers=a).status_code == 200

    print("ADMIN SCOPE TESTS OK")


if __name__ == "__main__":
    main()
