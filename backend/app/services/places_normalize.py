"""Нормализация адресов и geohash для справочника банкоматов."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

_STREET_PREFIX_RE = re.compile(
    r"^(?:ул\.?|улица|пр-?т\.?|проспект|пер\.?|переулок|б-?р\.?|бульвар|"
    r"наб\.?|набережная|пл\.?|площадь|ш\.?|шоссе|проезд|аллея)\s+",
    re.IGNORECASE,
)
_MULTI_SPACE_RE = re.compile(r"\s+")
_HOUSE_CORP_RE = re.compile(
    r"(?i)\s*(?:корп(?:ус)?\.?|к)\s*(\d+[а-яa-z]?)\s*"
)
_HOUSE_STR_RE = re.compile(r"(?i)\s*(?:стр(?:оение)?\.?)\s*(\d+[а-яa-z]?)\s*")


def _fold(text: str) -> str:
    return text.replace("ё", "е").replace("Ё", "е").strip().lower()


def normalize_city(value: str) -> str:
    return _MULTI_SPACE_RE.sub(" ", _fold(value or ""))


def normalize_street(value: str) -> str:
    text = _MULTI_SPACE_RE.sub(" ", _fold(value or ""))
    text = _STREET_PREFIX_RE.sub("", text)
    return text.strip(" ,.")


def normalize_house(value: Optional[str]) -> str:
    if not value:
        return ""
    text = _MULTI_SPACE_RE.sub(" ", _fold(value))
    text = text.replace("№", "").replace("дом", "").replace("д.", " ")
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    corp = ""
    m = _HOUSE_CORP_RE.search(text)
    if m:
        corp = "к" + m.group(1).lower()
        text = _HOUSE_CORP_RE.sub(" ", text)
    building = ""
    m = _HOUSE_STR_RE.search(text)
    if m:
        building = "с" + m.group(1).lower()
        text = _HOUSE_STR_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub("", text).strip(" ,./-")
    return f"{text}{corp}{building}"


def street_key(city_norm: str, street_norm: str) -> str:
    raw = f"{city_norm}|{street_norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    """Простой geohash без внешних зависимостей."""
    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0
    bits: list[int] = []
    even = True
    while len(bits) < precision * 5:
        if even:
            mid = (lon_min + lon_max) / 2
            if lon >= mid:
                bits.append(1)
                lon_min = mid
            else:
                bits.append(0)
                lon_max = mid
        else:
            mid = (lat_min + lat_max) / 2
            if lat >= mid:
                bits.append(1)
                lat_min = mid
            else:
                bits.append(0)
                lat_max = mid
        even = not even
    chars: list[str] = []
    for i in range(0, len(bits), 5):
        idx = 0
        for bit in bits[i : i + 5]:
            idx = (idx << 1) | bit
        chars.append(_BASE32[idx])
    return "".join(chars)


def geohash_neighbors(code: str) -> list[str]:
    """Ячейка и 8 соседей (для precision>=1). Упрощённо: сама ячейка + префикс-соседи."""
    if not code:
        return []
    # Для каркаса достаточно самой ячейки и укороченного префикса.
    result = {code}
    if len(code) > 1:
        result.add(code[:-1])
    return list(result)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def names_similar(a: str, b: str) -> bool:
    na = _MULTI_SPACE_RE.sub(" ", _fold(a))
    nb = _MULTI_SPACE_RE.sub(" ", _fold(b))
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na in nb or nb in na
