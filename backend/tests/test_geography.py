"""Smoke test: geography block in dashboard summary.

Run from backend/: python tests/test_geography.py
"""

from __future__ import annotations

import os
import pathlib
import sys

TEST_DB = pathlib.Path("data/test_geography.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["GEOCODE_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_geography.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import SessionLocal  # noqa: E402
from app.db.models import City  # noqa: E402
from app.main import app  # noqa: E402

OWNER = 111111111


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def seed_coords(city_id: int, lat: float, lon: float) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(City)
            .where(City.id == city_id)
            .values(lat=lat, lon=lon, geocode_failed=False)
        )
        await session.commit()


def main() -> None:
    import asyncio

    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}

        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "Казань", "status": "working"},
        )
        assert r.status_code == 201, r.text
        kazan = r.json()
        assert kazan["name"] == "Казань"

        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "Сочи", "status": "paused"},
        )
        assert r.status_code == 201, r.text
        sochi = r.json()

        r = client.post(
            "/api/cities",
            headers=owner,
            json={"name": "НесуществующийГородXYZ", "status": "stopped"},
        )
        assert r.status_code == 201, r.text

        # Без живого геокодера координаты проставляем вручную (как после Nominatim).
        asyncio.run(seed_coords(kazan["id"], 55.796, 49.106))
        asyncio.run(seed_coords(sochi["id"], 43.585, 39.723))

        r = client.get("/api/dashboard/summary", headers=owner)
        assert r.status_code == 200, r.text
        body = r.json()
        cities = body["cities"]
        assert cities["total"] == 3
        assert cities["working"] == 1
        assert cities["paused"] == 1
        assert cities["stopped"] == 1

        geo = cities["geography"]
        assert len(geo) == 3
        by_name = {row["name"]: row for row in geo}
        assert by_name["Казань"]["lat"] == 55.796
        assert by_name["Казань"]["lon"] == 49.106
        assert by_name["Казань"]["status"] == "working"
        assert by_name["Сочи"]["status"] == "paused"
        assert by_name["НесуществующийГородXYZ"]["lat"] is None
        print("geography summary ok")

        # Роль без cities:read не видит geography
        r = client.post(
            "/api/users",
            headers=owner,
            json={"telegram_id": 222222222, "role": "noga", "display_name": "Нога"},
        )
        assert r.status_code == 201, r.text
        # у noga есть cities:read — geography всё равно приходит
        noga = {"Authorization": "Bearer " + token(client, 222222222)}
        r = client.get("/api/dashboard/summary", headers=noga)
        assert r.status_code == 200, r.text
        assert len(r.json()["cities"]["geography"]) == 3
        print("noga sees geography ok")

    print("OK")


if __name__ == "__main__":
    main()
