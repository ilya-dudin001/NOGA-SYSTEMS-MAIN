"""Telegram WebApp initData validation (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl


class InitDataError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class TelegramUser:
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None
    photo_url: Optional[str] = None


@dataclass
class ValidatedInitData:
    user: TelegramUser
    auth_date: int
    query_id: Optional[str] = None
    raw: dict[str, str] | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> ValidatedInitData:
    if not init_data or not init_data.strip():
        raise InitDataError("BAD_SIGNATURE", "Empty initData")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("BAD_SIGNATURE", "Missing hash")

    # Telegram uses data_check_string = key=value pairs sorted, joined by \n
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    computed = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise InitDataError("BAD_SIGNATURE", "Invalid initData signature")

    auth_date_raw = parsed.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("EXPIRED", "Missing auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("EXPIRED", "Invalid auth_date") from exc

    now = int(time.time())
    if max_age_seconds > 0 and (now - auth_date) > max_age_seconds:
        raise InitDataError("EXPIRED", "initData expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise InitDataError("BAD_SIGNATURE", "Missing user in initData")

    try:
        user_obj: dict[str, Any] = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("BAD_SIGNATURE", "Invalid user JSON") from exc

    if "id" not in user_obj:
        raise InitDataError("BAD_SIGNATURE", "Missing user.id")

    user = TelegramUser(
        id=int(user_obj["id"]),
        first_name=user_obj.get("first_name"),
        last_name=user_obj.get("last_name"),
        username=user_obj.get("username"),
        language_code=user_obj.get("language_code"),
        is_premium=user_obj.get("is_premium"),
        photo_url=user_obj.get("photo_url"),
    )

    return ValidatedInitData(
        user=user,
        auth_date=auth_date,
        query_id=parsed.get("query_id"),
        raw=parsed,
    )
