"""SQLite-кэш адресов и объектов справочника банкоматов."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import PlaceAddressCache, PlaceKind, PlaceObjectCache
from app.services.places_normalize import (
    encode_geohash,
    geohash_neighbors,
    haversine_m,
    names_similar,
)


async def get_address(
    session: AsyncSession,
    *,
    city_norm: str,
    street_norm: str,
    house_norm: str,
) -> Optional[PlaceAddressCache]:
    result = await session.execute(
        select(PlaceAddressCache).where(
            PlaceAddressCache.city_norm == city_norm,
            PlaceAddressCache.street_norm == street_norm,
            PlaceAddressCache.house_norm == house_norm,
        )
    )
    return result.scalar_one_or_none()


async def upsert_address(
    session: AsyncSession,
    *,
    city_norm: str,
    street_norm: str,
    house_norm: str,
    lat: float,
    lon: float,
    provider: str,
    external_id: Optional[str],
) -> PlaceAddressCache:
    row = await get_address(
        session,
        city_norm=city_norm,
        street_norm=street_norm,
        house_norm=house_norm,
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = PlaceAddressCache(
            city_norm=city_norm,
            street_norm=street_norm,
            house_norm=house_norm,
            lat=lat,
            lon=lon,
            provider=provider,
            external_id=external_id,
            queried_at=now,
        )
        session.add(row)
    else:
        row.lat = lat
        row.lon = lon
        row.provider = provider
        row.external_id = external_id
        row.queried_at = now
    await session.flush()
    return row


def _ttl_cutoff() -> datetime:
    days = get_settings().places_cache_ttl_days
    return datetime.now(timezone.utc) - timedelta(days=days)


async def load_nearby_cached(
    session: AsyncSession,
    *,
    lat: float,
    lon: float,
    street_key: str,
    radius_m: int,
) -> list[dict[str, Any]]:
    cutoff = _ttl_cutoff()
    hashes = set(geohash_neighbors(encode_geohash(lat, lon, 7)))
    prefixes = {h[:6] for h in hashes if len(h) >= 6}
    # Берём по улице и по geohash-префиксу, дистанцию режем в Python.
    clauses = [PlaceObjectCache.street_key == street_key]
    if hashes:
        clauses.append(PlaceObjectCache.geohash.in_(list(hashes)))
    for prefix in prefixes:
        clauses.append(PlaceObjectCache.geohash.like(prefix + "%"))
    result = await session.execute(
        select(PlaceObjectCache).where(
            PlaceObjectCache.fetched_at >= cutoff,
            or_(*clauses),
        )
    )
    rows = list(result.scalars().all())
    items: list[dict[str, Any]] = []
    for row in rows:
        dist = haversine_m(lat, lon, row.lat, row.lon)
        if row.street_key == street_key:
            if dist > radius_m * 1.5:
                continue
        elif dist > radius_m * 1.25:
            continue
        items.append(
            {
                "kind": row.kind.value if isinstance(row.kind, PlaceKind) else str(row.kind),
                "name": row.name,
                "bank": row.bank,
                "address": row.address,
                "lat": row.lat,
                "lon": row.lon,
                "distance_m": round(dist),
                "source": row.source,
                "external_id": row.external_id,
                "from_cache": True,
            }
        )
    return items


async def upsert_objects(
    session: AsyncSession,
    *,
    items: list[dict[str, Any]],
    street_key: str,
) -> None:
    if not items:
        return
    now = datetime.now(timezone.utc)
    for item in items:
        source = str(item.get("source") or "2gis")
        external_id = str(item.get("external_id") or "")
        if not external_id:
            continue
        kind_raw = item.get("kind") or PlaceKind.poi.value
        try:
            kind = PlaceKind(kind_raw)
        except ValueError:
            kind = PlaceKind.poi
        lat = float(item["lat"])
        lon = float(item["lon"])
        result = await session.execute(
            select(PlaceObjectCache).where(
                PlaceObjectCache.source == source,
                PlaceObjectCache.external_id == external_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                PlaceObjectCache(
                    source=source,
                    external_id=external_id,
                    kind=kind,
                    name=str(item.get("name") or ""),
                    bank=item.get("bank"),
                    address=item.get("address"),
                    lat=lat,
                    lon=lon,
                    street_key=street_key,
                    geohash=encode_geohash(lat, lon, 7),
                    fetched_at=now,
                    payload=None,
                )
            )
        else:
            row.kind = kind
            row.name = str(item.get("name") or row.name)
            row.bank = item.get("bank")
            row.address = item.get("address")
            row.lat = lat
            row.lon = lon
            row.street_key = street_key or row.street_key
            row.geohash = encode_geohash(lat, lon, 7)
            row.fetched_at = now
    await session.flush()


def merge_items(
    cached: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge: API побеждает полями; объекты только из кэша остаются with from_cache."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    def put(item: dict[str, Any], *, prefer_fresh: bool) -> None:
        key = (str(item.get("source") or ""), str(item.get("external_id") or ""))
        if key[1]:
            existing = merged.get(key)
            if existing is None or prefer_fresh:
                merged[key] = dict(item)
            return
        # Без external_id — дедуп по имени + близости.
        for mkey, existing in list(merged.items()):
            if names_similar(str(existing.get("name") or ""), str(item.get("name") or "")):
                dist = haversine_m(
                    float(existing["lat"]),
                    float(existing["lon"]),
                    float(item["lat"]),
                    float(item["lon"]),
                )
                if dist < 50:
                    if prefer_fresh:
                        merged[mkey] = dict(item)
                    return
        # Синтетический ключ
        synth = (
            str(item.get("source") or "x"),
            f"name:{item.get('name')}:{round(float(item['lat']), 5)}",
        )
        if synth not in merged or prefer_fresh:
            merged[synth] = dict(item)

    for item in cached:
        put(item, prefer_fresh=False)
    for item in fresh:
        packed = dict(item)
        packed["from_cache"] = False
        put(packed, prefer_fresh=True)

    return list(merged.values())


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(kind: str) -> int:
        if kind in ("atm", "terminal"):
            return 0
        return 1

    return sorted(
        items,
        key=lambda it: (rank(str(it.get("kind") or "")), float(it.get("distance_m") or 0)),
    )
