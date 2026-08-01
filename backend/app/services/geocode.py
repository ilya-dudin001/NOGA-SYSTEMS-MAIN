"""Публичный геокодинг городов РФ: Nominatim (OSM), запасной — Photon."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import City

logger = logging.getLogger("noga.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "NOGA-Systems/1.0 (EM Operations dashboard; geography widget)"

# Nominatim: не чаще 1 запроса в секунду.
_last_nominatim_at = 0.0
_lock = asyncio.Lock()


async def ensure_schema(conn) -> None:  # noqa: ANN001
    """Добавить lat/lon/geocode_failed, если create_all их не довнёс (старая SQLite)."""
    if "sqlite" not in get_settings().database_url:
        return
    result = await conn.execute(text("PRAGMA table_info(cities)"))
    cols = {row[1] for row in result.fetchall()}
    if not cols:
        return
    if "lat" not in cols:
        await conn.execute(text("ALTER TABLE cities ADD COLUMN lat FLOAT"))
    if "lon" not in cols:
        await conn.execute(text("ALTER TABLE cities ADD COLUMN lon FLOAT"))
    if "geocode_failed" not in cols:
        await conn.execute(
            text(
                "ALTER TABLE cities ADD COLUMN geocode_failed BOOLEAN "
                "NOT NULL DEFAULT 0"
            )
        )


async def _throttle_nominatim() -> None:
    global _last_nominatim_at
    async with _lock:
        loop = asyncio.get_event_loop()
        now = loop.time()
        wait = 1.05 - (now - _last_nominatim_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_nominatim_at = loop.time()


async def lookup(name: str) -> Optional[tuple[float, float]]:
    """Вернуть (lat, lon) для города в РФ или None."""
    settings = get_settings()
    if not settings.geocode_enabled:
        return None
    cleaned = " ".join(name.split())
    if not cleaned:
        return None

    coords = await _nominatim(cleaned)
    if coords is not None:
        return coords
    return await _photon(cleaned)


async def _nominatim(name: str) -> Optional[tuple[float, float]]:
    await _throttle_nominatim()
    params = {
        "q": name,
        "format": "json",
        "limit": "1",
        "countrycodes": "ru",
        "accept-language": "ru",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
            if res.status_code != 200:
                logger.warning("nominatim status=%s name=%s", res.status_code, name)
                return None
            rows = res.json()
    except Exception:
        logger.exception("nominatim failed name=%s", name)
        return None
    if not rows:
        # Иногда помогает явное «Россия».
        await _throttle_nominatim()
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.get(
                    NOMINATIM_URL,
                    params={
                        "q": f"{name}, Россия",
                        "format": "json",
                        "limit": "1",
                        "countrycodes": "ru",
                        "accept-language": "ru",
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                rows = res.json() if res.status_code == 200 else []
        except Exception:
            logger.exception("nominatim retry failed name=%s", name)
            return None
    if not rows:
        return None
    try:
        return float(rows[0]["lat"]), float(rows[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


async def _photon(name: str) -> Optional[tuple[float, float]]:
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(
                PHOTON_URL,
                params={"q": f"{name}, Russia", "limit": 1},
                headers={"User-Agent": USER_AGENT},
            )
            if res.status_code != 200:
                return None
            features = (res.json() or {}).get("features") or []
    except Exception:
        logger.exception("photon failed name=%s", name)
        return None
    if not features:
        return None
    try:
        coords = features[0]["geometry"]["coordinates"]
        lon, lat = float(coords[0]), float(coords[1])
        # Photon без country filter — отсекаем явный мусор вне РФ.
        if not (41.0 <= lat <= 82.0 and (19.0 <= lon <= 180.0 or -180.0 <= lon <= -169.0)):
            return None
        return lat, lon
    except (KeyError, TypeError, ValueError, IndexError):
        return None


async def ensure_city_coords(session: AsyncSession, city: City) -> bool:
    """Заполнить lat/lon у города, если ещё нет. True — координаты есть."""
    if city.lat is not None and city.lon is not None:
        return True
    if city.geocode_failed:
        return False
    coords = await lookup(city.name)
    if coords is None:
        city.geocode_failed = True
        await session.flush()
        return False
    city.lat, city.lon = coords
    city.geocode_failed = False
    await session.flush()
    return True


def clear_coords(city: City) -> None:
    """Сброс при переименовании — координаты пересчитаем заново."""
    city.lat = None
    city.lon = None
    city.geocode_failed = False


async def fill_missing(
    session: AsyncSession, *, limit: int = 5
) -> int:
    """Догеокодировать до limit городов без координат. Возвращает число попыток."""
    settings = get_settings()
    if not settings.geocode_enabled:
        return 0
    result = await session.execute(
        select(City)
        .where(City.lat.is_(None), City.geocode_failed.is_(False))
        .order_by(City.id.asc())
        .limit(limit)
    )
    cities = list(result.scalars().all())
    done = 0
    for city in cities:
        await ensure_city_coords(session, city)
        done += 1
    return done
