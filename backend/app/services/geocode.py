"""Публичный геокодинг: Nominatim / Photon.

lookup() — координаты для карты РФ.
suggest() — автодополнение городов (с опечатками) и валюта страны.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import City, Currency

logger = logging.getLogger("noga.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_LOOKUP_URL = "https://nominatim.openstreetmap.org/lookup"
PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "NOGA-Systems/1.0 (EM Operations dashboard; geography widget)"

# ISO 3166-1 alpha-2 → валюта из справочника системы.
COUNTRY_CURRENCY: dict[str, Currency] = {
    "RU": Currency.RUB,
    "UZ": Currency.UZS,
    "KG": Currency.KGS,
    "KZ": Currency.KZT,
    "AZ": Currency.AZN,
    "BY": Currency.BYN,
    "MD": Currency.MDL,
    # Приднестровье в OSM иногда отдельным кодом.
    "PMR": Currency.PRB,
    "US": Currency.USD,
}

PLACE_VALUES = frozenset(
    {"city", "town", "village", "municipality", "hamlet", "suburb", "neighbourhood"}
)

SUPPORTED_SUGGEST_LANGS = frozenset({"ru", "en"})

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


def normalize_suggest_lang(lang: Optional[str]) -> str:
    """ru / en — по языку Telegram или браузера; иначе русский."""
    if not lang:
        return "ru"
    code = lang.strip().lower().replace("_", "-")
    if code.startswith("ru"):
        return "ru"
    if code.startswith("en"):
        return "en"
    return "en"


def currency_for_country(country_code: Optional[str]) -> Optional[Currency]:
    if not country_code:
        return None
    return COUNTRY_CURRENCY.get(country_code.strip().upper())


def _osm_prefix(osm_type: Any) -> str:
    token = str(osm_type or "").strip().upper()
    if token.startswith("R") or token == "RELATION":
        return "R"
    if token.startswith("W") or token == "WAY":
        return "W"
    return "N"


def _pick_localized_name(item: dict[str, Any], lang: str) -> Optional[str]:
    """Имя на нужном языке: name:lang → name из accept-language → address."""
    details = item.get("namedetails") or {}
    preferred = details.get(f"name:{lang}")
    if preferred:
        return str(preferred).strip()
    # Английский часто лежит в int_name / name:en.
    if lang == "en":
        for key in ("name:en", "int_name", "name"):
            value = details.get(key)
            if value:
                return str(value).strip()
    if lang == "ru":
        for key in ("name:ru", "name"):
            value = details.get(key)
            if value:
                return str(value).strip()
    address = item.get("address") or {}
    for key in ("city", "town", "village", "municipality"):
        value = address.get(key)
        if value:
            return str(value).strip()
    name = item.get("name")
    return str(name).strip() if name else None


def _norm_place_token(value: str) -> str:
    """Схлопывает дефисы/пробелы и ё→е для сравнения «Кишинев» ↔ «Кишинёв»."""
    out: list[str] = []
    for ch in value.casefold():
        if ch == "ё":
            ch = "е"
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def _match_score(name: str, query: str) -> float:
    """0..1: насколько имя похоже на запрос (без учёта ранга геокодера)."""
    n = _norm_place_token(name)
    q = _norm_place_token(query)
    if not n or not q:
        return 0.0
    if n == q:
        return 1.0
    # Запрос — префикс имени: пользователь ещё допечатывает («Киш» → «Кишинёв»).
    if n.startswith(q):
        return 0.9
    # Имя — короткий префикс запроса: «Кишин» не должен затмевать «Кишинёв».
    if q.startswith(n):
        ratio = len(n) / len(q)
        if ratio >= 0.85:
            return 0.9
        return ratio * 0.6
    common = 0
    for a, b in zip(n, q):
        if a != b:
            break
        common += 1
    return common / max(len(n), len(q))


def _is_city_like(item: dict[str, Any]) -> bool:
    """place=* или admin-граница города (у Алматы class=boundary, addresstype=city)."""
    kind = (item.get("type") or "").lower()
    cls = (item.get("class") or "").lower()
    address_type = (item.get("addresstype") or "").lower()
    if kind in PLACE_VALUES or address_type in PLACE_VALUES:
        return True
    if cls == "place":
        return True
    return False


def _pack_suggest_row(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = (row.get("name") or "").strip()
    if not name:
        return None
    code = (row.get("country_code") or "").upper()
    country = (row.get("country") or "").strip()
    currency = currency_for_country(code)
    return {
        "name": name,
        "country": country or None,
        "country_code": code or None,
        "currency": currency.value if currency else None,
        "label": name if not country else f"{name} · {country}",
    }


def _finalize_suggest(
    rows: list[dict[str, Any]], *, limit: int, query: str = ""
) -> list[dict[str, Any]]:
    """Дедуп: сначала страны из справочника валют, затем похожесть на запрос."""
    # Валютный приоритет важнее score: после локализации «Bakı»→«Баку»
    # латиница «Baku» даёт score 0, а тёзки без валюты — 1.0.
    indexed = list(enumerate(rows))
    indexed.sort(
        key=lambda pair: (
            0 if currency_for_country(pair[1].get("country_code")) else 1,
            -_match_score(pair[1].get("name") or "", query) if query else 0.0,
            pair[0],
        )
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in indexed:
        packed = _pack_suggest_row(row)
        if not packed:
            continue
        key = f"{packed['name'].casefold()}|{(packed.get('country_code') or '')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(packed)
        if len(out) >= limit:
            break
    return out


async def suggest(
    query: str, *, limit: int = 3, lang: Optional[str] = None
) -> list[dict[str, Any]]:
    """1–3 варианта города: Photon (опечатки) + перевод через Nominatim.

    Каждый элемент: name, country, country_code, currency, label.
    """
    settings = get_settings()
    if not settings.geocode_enabled:
        return []
    cleaned = " ".join(query.split())
    if len(cleaned) < 2:
        return []
    limit = max(1, min(limit, 5))
    locale = normalize_suggest_lang(lang)

    candidates = await _photon_suggest(cleaned, fetch=max(limit * 4, 8))
    # Берём запас: финальный limit отрежем после ранжирования.
    localized = await _localize_candidates(
        candidates, lang=locale, limit=max(limit * 3, 6)
    )
    best = max((_match_score(r.get("name") or "", cleaned) for r in localized), default=0.0)
    # #region agent log
    try:
        import json as _json
        from pathlib import Path as _Path

        _log = {
            "sessionId": "328f38",
            "location": "geocode.py:suggest",
            "message": "suggest_path",
            "hypothesisId": "H-Baku",
            "timestamp": int(__import__("time").time() * 1000),
            "data": {
                "query": cleaned,
                "norm_q": _norm_place_token(cleaned),
                "photon_count": len(candidates),
                "photon": [
                    {
                        "name": c.get("name"),
                        "cc": c.get("country_code"),
                        "osm": f"{c.get('osm_type')}:{c.get('osm_id')}",
                    }
                    for c in candidates[:8]
                ],
                "localized": [
                    {
                        "name": r.get("name"),
                        "cc": r.get("country_code"),
                        "score": round(
                            _match_score(r.get("name") or "", cleaned), 3
                        ),
                    }
                    for r in localized
                ],
                "best": round(best, 3),
                "use_photon_exact": bool(localized) and best >= 1.0,
                "runId": "baku-post-fix",
            },
        }
        _Path(__file__).resolve().parents[3].joinpath("debug-328f38.log").open(
            "a", encoding="utf-8"
        ).write(_json.dumps(_log, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    # Только точное совпадение Photon — без Nominatim (rate limit).
    # Prefix 0.9 («Бакур» на запрос «Баку») раньше отрезал настоящий город.
    if localized and best >= 1.0:
        return _finalize_suggest(localized, limit=limit, query=cleaned)

    rows = await _nominatim_suggest(cleaned, fetch=max(limit * 3, 6), lang=locale)
    # #region agent log
    try:
        import json as _json
        from pathlib import Path as _Path

        _log2 = {
            "sessionId": "328f38",
            "location": "geocode.py:suggest:nominatim",
            "message": "nominatim_fallback",
            "hypothesisId": "H-Baku",
            "timestamp": int(__import__("time").time() * 1000),
            "data": {
                "query": cleaned,
                "nominatim": [
                    {"name": r.get("name"), "cc": r.get("country_code")}
                    for r in rows[:8]
                ],
                "final": _finalize_suggest(
                    list(localized) + list(rows), limit=limit, query=cleaned
                ),
                "runId": "baku-post-fix",
            },
        }
        _Path(__file__).resolve().parents[3].joinpath("debug-328f38.log").open(
            "a", encoding="utf-8"
        ).write(_json.dumps(_log2, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    return _finalize_suggest(list(localized) + list(rows), limit=limit, query=cleaned)


async def _localize_candidates(
    candidates: list[dict[str, Any]], *, lang: str, limit: int
) -> list[dict[str, Any]]:
    """Переводит кандидатов Photon через Nominatim lookup + namedetails."""
    osm_ids: list[str] = []
    seen_osm: set[str] = set()
    for row in candidates:
        osm_id = row.get("osm_id")
        if osm_id is None:
            continue
        key = f"{_osm_prefix(row.get('osm_type'))}{osm_id}"
        if key in seen_osm:
            continue
        seen_osm.add(key)
        osm_ids.append(key)
        if len(osm_ids) >= max(limit * 3, 6):
            break
    if not osm_ids:
        return []

    await _throttle_nominatim()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(
                NOMINATIM_LOOKUP_URL,
                params={
                    "osm_ids": ",".join(osm_ids),
                    "format": "json",
                    "addressdetails": "1",
                    "namedetails": "1",
                    "accept-language": lang,
                },
                headers={"User-Agent": USER_AGENT},
            )
            if res.status_code != 200:
                logger.warning("nominatim lookup status=%s", res.status_code)
                return []
            items = res.json() or []
    except Exception:
        logger.exception("nominatim lookup failed")
        return []

    by_osm: dict[str, dict[str, Any]] = {}
    for item in items:
        osm_type = item.get("osm_type")
        osm_id = item.get("osm_id")
        if osm_id is None:
            continue
        key = f"{_osm_prefix(osm_type)}{osm_id}"
        address = item.get("address") or {}
        name = _pick_localized_name(item, lang)
        if not name:
            continue
        code = (address.get("country_code") or "").upper()
        country = (address.get("country") or "").strip() or None
        by_osm[key] = {
            "name": name,
            "country": country,
            "country_code": code or None,
        }

    # Порядок Photon важнее алфавита: иначе «Алматы» тонет под «Алмалы*».
    rows: list[dict[str, Any]] = []
    for key in osm_ids:
        row = by_osm.get(key)
        if row:
            rows.append(row)

    return _finalize_suggest(rows, limit=limit)


async def _photon_suggest(query: str, *, fetch: int) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = [
        ("q", query),
        ("limit", str(fetch)),
        ("lang", "default"),
        ("osm_tag", "place:city"),
        ("osm_tag", "place:town"),
        ("osm_tag", "place:village"),
    ]
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(
                PHOTON_URL, params=params, headers={"User-Agent": USER_AGENT}
            )
            if res.status_code != 200:
                logger.warning("photon suggest status=%s q=%s", res.status_code, query)
                return []
            features = (res.json() or {}).get("features") or []
    except Exception:
        logger.exception("photon suggest failed q=%s", query)
        return []

    rows: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        osm_value = (props.get("osm_value") or props.get("type") or "").lower()
        if osm_value and osm_value not in PLACE_VALUES and props.get("osm_key") != "place":
            continue
        osm_id = props.get("osm_id")
        if osm_id is None:
            continue
        name = props.get("name") or props.get("city") or props.get("town") or ""
        rows.append(
            {
                "name": str(name).strip(),
                "country": (props.get("country") or "").strip() or None,
                "country_code": (props.get("countrycode") or "").strip().upper() or None,
                "osm_type": props.get("osm_type"),
                "osm_id": osm_id,
            }
        )
    return rows


async def _nominatim_suggest(
    query: str, *, fetch: int, lang: str = "ru"
) -> list[dict[str, Any]]:
    await _throttle_nominatim()
    params = {
        "q": query,
        "format": "json",
        "addressdetails": "1",
        "namedetails": "1",
        "limit": str(fetch),
        "accept-language": lang,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(
                NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}
            )
            if res.status_code != 200:
                return []
            data = res.json() or []
    except Exception:
        logger.exception("nominatim suggest failed q=%s", query)
        return []

    rows: list[dict[str, Any]] = []
    for item in data:
        if not _is_city_like(item):
            continue
        address = item.get("address") or {}
        name = _pick_localized_name(item, lang)
        if not name:
            continue
        code = (address.get("country_code") or "").upper()
        rows.append(
            {
                "name": name,
                "country": (address.get("country") or "").strip() or None,
                "country_code": code or None,
            }
        )
    return rows


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


async def fill_missing(session: AsyncSession, *, limit: int = 5) -> int:
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
