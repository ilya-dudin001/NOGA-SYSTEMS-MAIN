"""Smoke test: подсказки городов и валюта страны.

Run from backend/: python tests/test_city_suggest.py
"""

from __future__ import annotations

import os
import pathlib
import sys
from unittest.mock import AsyncMock, patch

TEST_DB = pathlib.Path("data/test_city_suggest.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["GEOCODE_ENABLED"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_city_suggest.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402
from app.services import geocode as geocode_service  # noqa: E402

OWNER = 111111111


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main() -> None:
    assert geocode_service.currency_for_country("uz").value == "UZS"
    assert geocode_service.currency_for_country("RU").value == "RUB"
    assert geocode_service.currency_for_country("XX") is None
    print("country->currency map ok")

    fake = [
        {
            "name": "Ташкент",
            "country": "Узбекистан",
            "country_code": "UZ",
            "currency": "UZS",
            "label": "Ташкент · Узбекистан",
        },
        {
            "name": "Казань",
            "country": "Россия",
            "country_code": "RU",
            "currency": "RUB",
            "label": "Казань · Россия",
        },
    ]

    with patch.object(
        geocode_service, "suggest", new=AsyncMock(return_value=fake)
    ):
        with TestClient(app) as client:
            owner = {"Authorization": "Bearer " + token(client, OWNER)}
            r = client.get("/api/cities/suggest?q=таш", headers=owner)
            assert r.status_code == 200, r.text
            rows = r.json()
            assert len(rows) == 2
            assert rows[0]["name"] == "Ташкент"
            assert rows[0]["currency"] == "UZS"
            assert rows[1]["currency"] == "RUB"
            print("suggest endpoint ok")

            r = client.get("/api/cities/suggest?q=a", headers=owner)
            assert r.status_code == 422, r.text
            print("short query → 422 ok")

    # Живой Photon (опечатка Tashke → Ташкент/Toshkent)
    import asyncio

    rows = asyncio.run(geocode_service.suggest("Tashke", limit=3))
    assert rows, "photon should return something for Tashke"
    assert any(r.get("currency") == "UZS" for r in rows), rows
    print("live photon typo suggest ok:", [r["label"] for r in rows])

    print("OK")


if __name__ == "__main__":
    main()
