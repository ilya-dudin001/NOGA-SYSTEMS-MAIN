"""Клиент 2ГИС Places/Geocoder. Без ключа — детерминированные моки для dev."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.db.models import PlaceKind
from app.services.places_normalize import haversine_m

logger = logging.getLogger("noga.places.dgis")

GEOCODER_URL = "https://catalog.api.2gis.com/3.0/items/geocode"
ITEMS_URL = "https://catalog.api.2gis.com/3.0/items"

# Текстовые запросы, пока rubric_id не зафиксированы ключом.
ATM_QUERIES = ("банкомат", "платёжный терминал")
POI_QUERIES = (
    "торговый центр",
    "супермаркет",
    "гипермаркет",
    "мегамаркет",
)

_BANK_HINTS = (
    "сбер",
    "сбербанк",
    "втб",
    "альфа",
    "тинькофф",
    "т-банк",
    "газпромбанк",
    "открытие",
    "райффайзен",
    "совкомбанк",
    "росбанк",
    "юникредит",
    "почта банк",
    "mkb",
    "мкб",
)


class PlacesProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _has_key() -> bool:
    return bool((get_settings().dgis_api_key or "").strip())


def _mock_point(city: str, street: str, house: str) -> tuple[float, float, str]:
    digest = hashlib.md5(f"{city}|{street}|{house}".encode("utf-8")).hexdigest()
    # Базовая точка около центра Москвы + небольшой сдвиг по улице.
    lat = 55.75 + (int(digest[:4], 16) % 2000) / 100000.0
    lon = 37.62 + (int(digest[4:8], 16) % 2000) / 100000.0
    return lat, lon, f"mock-{digest[:12]}"


def _offset_point(lat: float, lon: float, seed: str, meters: float) -> tuple[float, float]:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    angle = (int(digest[:4], 16) % 360) * 0.017453292519943295
    dlat = (meters / 111320.0) * math.cos(angle)
    denom = 111320.0 * max(0.2, math.cos(lat * 0.017453292519943295))
    dlon = (meters / denom) * math.sin(angle)
    return lat + dlat, lon + dlon


def guess_bank(name: str) -> Optional[str]:
    low = (name or "").lower().replace("ё", "е")
    for hint in _BANK_HINTS:
        if hint in low:
            # Нормализованная подпись для UI.
            labels = {
                "сбер": "Сбербанк",
                "сбербанк": "Сбербанк",
                "втб": "ВТБ",
                "альфа": "Альфа-Банк",
                "тинькофф": "Т-Банк",
                "т-банк": "Т-Банк",
                "газпромбанк": "Газпромбанк",
                "открытие": "Открытие",
                "райффайзен": "Райффайзенбанк",
                "совкомбанк": "Совкомбанк",
                "росбанк": "Росбанк",
                "юникредит": "ЮниКредит",
                "почта банк": "Почта Банк",
                "mkb": "МКБ",
                "мкб": "МКБ",
            }
            return labels.get(hint, hint.title())
    return None


def _kind_from_name(name: str, default: PlaceKind) -> PlaceKind:
    low = (name or "").lower()
    if "терминал" in low:
        return PlaceKind.terminal
    if "банкомат" in low or "atm" in low:
        return PlaceKind.atm
    return default


def _pack_item(
    *,
    kind: PlaceKind,
    name: str,
    lat: float,
    lon: float,
    address: Optional[str],
    external_id: str,
    center: tuple[float, float],
    bank: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "kind": kind.value,
        "name": name,
        "bank": bank if bank is not None else guess_bank(name),
        "address": address,
        "lat": lat,
        "lon": lon,
        "distance_m": round(haversine_m(center[0], center[1], lat, lon)),
        "source": "2gis",
        "external_id": str(external_id),
        "from_cache": False,
    }


async def geocode_address(
    *, city: str, street: str, house: str = ""
) -> dict[str, Any]:
    """Вернуть {lat, lon, external_id, provider}."""
    if not _has_key():
        lat, lon, ext = _mock_point(city, street, house)
        return {
            "lat": lat,
            "lon": lon,
            "external_id": ext,
            "provider": "mock",
        }

    settings = get_settings()
    q = ", ".join(part for part in (city, street, house) if part)
    params = {
        "q": q,
        "fields": "items.point,items.full_address_name",
        "key": settings.dgis_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.places_api_timeout_sec) as client:
            res = await client.get(GEOCODER_URL, params=params)
    except httpx.HTTPError as exc:
        logger.exception("2gis geocode failed")
        raise PlacesProviderError(
            "PLACES_PROVIDER_ERROR", "Не удалось обратиться к картографическому сервису"
        ) from exc

    if res.status_code >= 400:
        logger.warning("2gis geocode status=%s body=%s", res.status_code, res.text[:300])
        raise PlacesProviderError(
            "PLACES_PROVIDER_ERROR", "Картографический сервис вернул ошибку"
        )

    data = res.json()
    items = (data.get("result") or {}).get("items") or []
    if not items:
        raise PlacesProviderError(
            "GEOCODE_FAILED", "Не удалось найти указанный адрес"
        )
    item = items[0]
    point = item.get("point") or {}
    lat = point.get("lat")
    lon = point.get("lon")
    if lat is None or lon is None:
        raise PlacesProviderError(
            "GEOCODE_FAILED", "Не удалось найти указанный адрес"
        )
    return {
        "lat": float(lat),
        "lon": float(lon),
        "external_id": str(item.get("id") or ""),
        "provider": "2gis",
    }


async def _search_query(
    client: httpx.AsyncClient,
    *,
    q: str,
    lat: float,
    lon: float,
    radius_m: int,
    key: str,
) -> list[dict[str, Any]]:
    params = {
        "q": q,
        "point": f"{lon},{lat}",
        "radius": radius_m,
        "sort": "distance",
        "fields": "items.point,items.full_address_name,items.address_name,items.name",
        "page_size": 10,
        "key": key,
    }
    res = await client.get(ITEMS_URL, params=params)
    if res.status_code >= 400:
        logger.warning("2gis items status=%s q=%s", res.status_code, q)
        return []
    data = res.json()
    return list((data.get("result") or {}).get("items") or [])


def _mock_search(lat: float, lon: float) -> list[dict[str, Any]]:
    center = (lat, lon)
    rows: list[dict[str, Any]] = []
    samples = [
        (PlaceKind.atm, "Сбербанк, банкомат", 80),
        (PlaceKind.atm, "ВТБ, банкомат", 140),
        (PlaceKind.terminal, "Платёжный терминал QIWI", 200),
        (PlaceKind.poi, "ТЦ Галерея", 350),
        (PlaceKind.poi, "Супермаркет Перекрёсток", 420),
    ]
    for kind, name, meters in samples:
        plat, plon = _offset_point(lat, lon, name, float(meters))
        rows.append(
            _pack_item(
                kind=kind,
                name=name,
                lat=plat,
                lon=plon,
                address=None,
                external_id=f"mock-{hashlib.md5(name.encode()).hexdigest()[:10]}",
                center=center,
            )
        )
    return rows


async def search_nearby(
    *, lat: float, lon: float, radius_m: Optional[int] = None
) -> list[dict[str, Any]]:
    """Банкоматы/терминалы + крупные POI вокруг точки."""
    settings = get_settings()
    radius = radius_m if radius_m is not None else settings.places_radius_m
    center = (lat, lon)

    if not _has_key():
        return _mock_search(lat, lon)

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=settings.places_api_timeout_sec) as client:
            for q in ATM_QUERIES:
                for item in await _search_query(
                    client,
                    q=q,
                    lat=lat,
                    lon=lon,
                    radius_m=radius,
                    key=settings.dgis_api_key,
                ):
                    ext = str(item.get("id") or "")
                    if not ext or ext in seen:
                        continue
                    point = item.get("point") or {}
                    plat, plon = point.get("lat"), point.get("lon")
                    if plat is None or plon is None:
                        continue
                    seen.add(ext)
                    name = item.get("name") or q
                    collected.append(
                        _pack_item(
                            kind=_kind_from_name(name, PlaceKind.atm),
                            name=name,
                            lat=float(plat),
                            lon=float(plon),
                            address=item.get("full_address_name")
                            or item.get("address_name"),
                            external_id=ext,
                            center=center,
                        )
                    )
            for q in POI_QUERIES:
                for item in await _search_query(
                    client,
                    q=q,
                    lat=lat,
                    lon=lon,
                    radius_m=radius,
                    key=settings.dgis_api_key,
                ):
                    ext = str(item.get("id") or "")
                    if not ext or ext in seen:
                        continue
                    point = item.get("point") or {}
                    plat, plon = point.get("lat"), point.get("lon")
                    if plat is None or plon is None:
                        continue
                    seen.add(ext)
                    name = item.get("name") or q
                    collected.append(
                        _pack_item(
                            kind=PlaceKind.poi,
                            name=name,
                            lat=float(plat),
                            lon=float(plon),
                            address=item.get("full_address_name")
                            or item.get("address_name"),
                            external_id=ext,
                            center=center,
                        )
                    )
    except httpx.HTTPError as exc:
        logger.exception("2gis search failed")
        raise PlacesProviderError(
            "PLACES_PROVIDER_ERROR", "Не удалось обратиться к картографическому сервису"
        ) from exc

    return collected
