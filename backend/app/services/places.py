"""Оркестратор справочника банкоматов: геокод → кэш → 2ГИС → merge."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services import places_cache
from app.services import places_dgis
from app.services.places_dgis import PlacesProviderError
from app.services.places_normalize import (
    normalize_city,
    normalize_house,
    normalize_street,
    street_key,
)

logger = logging.getLogger("noga.places")


class PlacesError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


async def search_nearby(
    session: AsyncSession,
    *,
    city: str,
    street: str,
    house: Optional[str] = None,
) -> dict[str, Any]:
    city_norm = normalize_city(city)
    street_norm = normalize_street(street)
    house_norm = normalize_house(house)
    if not city_norm or not street_norm:
        raise PlacesError("BAD_REQUEST", "Укажите город и улицу")

    settings = get_settings()
    radius = settings.places_radius_m
    skey = street_key(city_norm, street_norm)

    cached_addr = await places_cache.get_address(
        session,
        city_norm=city_norm,
        street_norm=street_norm,
        house_norm=house_norm,
    )
    if cached_addr is not None:
        lat, lon = cached_addr.lat, cached_addr.lon
    else:
        try:
            geo = await places_dgis.geocode_address(
                city=city_norm, street=street_norm, house=house_norm
            )
        except PlacesProviderError as exc:
            raise PlacesError(exc.code, exc.message) from exc
        lat = float(geo["lat"])
        lon = float(geo["lon"])
        await places_cache.upsert_address(
            session,
            city_norm=city_norm,
            street_norm=street_norm,
            house_norm=house_norm,
            lat=lat,
            lon=lon,
            provider=str(geo.get("provider") or "2gis"),
            external_id=geo.get("external_id"),
        )

    cached_items = await places_cache.load_nearby_cached(
        session,
        lat=lat,
        lon=lon,
        street_key=skey,
        radius_m=radius,
    )

    partial = False
    fresh: list[dict[str, Any]] = []
    try:
        fresh = await asyncio.wait_for(
            places_dgis.search_nearby(lat=lat, lon=lon, radius_m=radius),
            timeout=settings.places_api_timeout_sec,
        )
    except asyncio.TimeoutError:
        logger.warning("places provider timeout city=%s street=%s", city_norm, street_norm)
        partial = True
    except PlacesProviderError as exc:
        if not cached_items:
            raise PlacesError(exc.code, exc.message) from exc
        logger.warning("places provider error, serving cache: %s", exc.message)
        partial = True

    if fresh:
        await places_cache.upsert_objects(session, items=fresh, street_key=skey)

    merged = places_cache.sort_items(places_cache.merge_items(cached_items, fresh))
    return {
        "query": {
            "city": city_norm,
            "street": street_norm,
            "house": house_norm or None,
        },
        "center": {"lat": lat, "lon": lon},
        "partial": partial,
        "items": merged,
    }
