"""Справочник банкоматов: нормализация, кэш, API.

Run from backend/: python tests/test_places.py
"""

from __future__ import annotations

import os
import pathlib
import sys
from unittest.mock import AsyncMock, patch

TEST_DB = pathlib.Path("data/test_places.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["GEOCODE_ENABLED"] = "false"
os.environ["PLACES_ENABLED"] = "true"
os.environ["DGIS_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_places.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"
os.environ["CHAT_ENABLED"] = "false"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402
from app.services import places_normalize  # noqa: E402

OWNER = 111111111
NOGA_TG = 444444444


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_normalize() -> None:
    assert places_normalize.normalize_city("  Москва ") == "москва"
    assert places_normalize.normalize_street("ул. Тверская") == "тверская"
    assert places_normalize.normalize_street("проспект Мира") == "мира"
    assert places_normalize.normalize_house("15 корп. 2") == "15к2"
    assert places_normalize.normalize_house("д. 10") == "10"
    assert places_normalize.normalize_house(None) == ""
    key1 = places_normalize.street_key("москва", "тверская")
    key2 = places_normalize.street_key("москва", "тверская")
    assert key1 == key2
    gh = places_normalize.encode_geohash(55.75, 37.62, 7)
    assert len(gh) == 7
    assert places_normalize.haversine_m(55.75, 37.62, 55.75, 37.62) < 1
    print("normalize ok")


def main() -> None:
    test_normalize()

    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}

        r = client.get("/api/me", headers=owner)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["features"]["places"] is True
        assert "places:read" in me["permissions"]
        print("features.places ok")

        r = client.post(
            "/api/users",
            headers=owner,
            json={
                "telegram_id": NOGA_TG,
                "role": "noga",
                "display_name": "Нога Тест",
            },
        )
        assert r.status_code == 201, r.text
        noga = {"Authorization": "Bearer " + token(client, NOGA_TG)}

        r = client.post(
            "/api/places/nearby",
            headers=noga,
            json={"city": "Москва", "street": "ул. Тверская", "house": "10"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["center"]["lat"]
        assert data["items"], data
        kinds = [item["kind"] for item in data["items"]]
        assert "atm" in kinds or "terminal" in kinds
        # ATM/terminal раньше poi
        first_poi = next(
            (i for i, it in enumerate(data["items"]) if it["kind"] == "poi"), None
        )
        last_atm = max(
            (i for i, it in enumerate(data["items"]) if it["kind"] in ("atm", "terminal")),
            default=-1,
        )
        if first_poi is not None:
            assert last_atm < first_poi
        print("nearby mock + noga access ok:", len(data["items"]))

        # Второй адрес на той же улице: объекты из кэша видны даже без новых точек API
        empty_fresh: list = []
        with patch(
            "app.services.places_dgis.search_nearby",
            new=AsyncMock(return_value=empty_fresh),
        ):
            r = client.post(
                "/api/places/nearby",
                headers=owner,
                json={"city": "Москва", "street": "Тверская", "house": "15"},
            )
            assert r.status_code == 200, r.text
            cached = r.json()
            assert cached["items"], "ожидали объекты из кэша той же улицы"
            assert any(it.get("from_cache") for it in cached["items"]), cached["items"]
            print("street cache reuse ok:", len(cached["items"]))

    # Флаг выключен → 404
    os.environ["PLACES_ENABLED"] = "false"
    get_settings.cache_clear()
    # Нужен новый app-контекст настроек — TestClient уже держал app;
    # проверяем через Depends get_settings на уже импортированном app:
    # перечитываем settings в require_places_enabled через get_settings().
    with TestClient(app) as client:
        # get_settings закэширован с PLACES_ENABLED=false после cache_clear
        owner = {"Authorization": "Bearer " + token(client, OWNER)}
        r = client.get("/api/me", headers=owner)
        assert r.json()["features"]["places"] is False
        r = client.post(
            "/api/places/nearby",
            headers=owner,
            json={"city": "Москва", "street": "Тверская"},
        )
        assert r.status_code == 404, r.text
        print("places disabled -> 404 ok")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
