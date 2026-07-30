"""Telegram WebApp initData validation (server-side only)."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl

from kelbet.domain.enums import Language
from kelbet.domain.exceptions import ExpiredInitDataError, InvalidInitDataError


@dataclass(frozen=True, slots=True)
class TelegramWebAppUser:
    id: int
    username: str | None
    language_code: str | None
    first_name: str | None
    last_name: str | None
    is_premium: bool | None
    allows_write_to_pm: bool | None


@dataclass(frozen=True, slots=True)
class ValidatedInitData:
    user: TelegramWebAppUser
    auth_date: datetime
    raw_hash: str
    init_data_hash: str
    query_id: str | None


def hash_init_data(init_data: str) -> str:
    return hashlib.sha256(init_data.encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_language(language_code: str | None, *, default: Language = Language.KK) -> Language:
    if language_code is None:
        return default
    normalized = language_code.strip().lower()
    if normalized.startswith("ru"):
        return Language.RU
    if normalized.startswith("kk") or normalized.startswith("kz"):
        return Language.KK
    return default


def _build_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def compute_init_data_hash(init_data: str, bot_token: str) -> str:
    pairs = parse_qsl(init_data, keep_blank_values=True)
    filtered = [(k, v) for k, v in pairs if k != "hash"]
    if not filtered:
        raise InvalidInitDataError("initData has no fields")
    filtered.sort(key=lambda item: item[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in filtered)
    secret = _build_secret_key(bot_token)
    return hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Build a signed initData query string (tests / fixtures only)."""
    pairs = sorted((k, v) for k, v in fields.items() if k != "hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret = _build_secret_key(bot_token)
    digest = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    return urlencode([*pairs, ("hash", digest)])


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> ValidatedInitData:
    if not init_data or not init_data.strip():
        raise InvalidInitDataError("initData is empty")
    if not bot_token:
        raise InvalidInitDataError("bot token is not configured")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.get("hash")
    if not received_hash:
        raise InvalidInitDataError("initData missing hash")

    expected = compute_init_data_hash(init_data, bot_token)
    if not hmac.compare_digest(expected, received_hash):
        raise InvalidInitDataError("initData hash mismatch")

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw is None:
        raise InvalidInitDataError("initData missing auth_date")
    try:
        auth_ts = int(auth_date_raw)
    except ValueError as exc:
        raise InvalidInitDataError("auth_date is not an integer") from exc

    auth_date = datetime.fromtimestamp(auth_ts, tz=UTC)
    current = now or datetime.now(UTC)
    age = (current - auth_date).total_seconds()
    if age < -60:
        raise ExpiredInitDataError("auth_date is in the future")
    if age > max_age_seconds:
        raise ExpiredInitDataError("auth_date expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InvalidInitDataError("initData missing user")
    try:
        user_obj: dict[str, Any] = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InvalidInitDataError("user JSON is invalid") from exc

    try:
        telegram_id = int(user_obj["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidInitDataError("user.id is required") from exc

    user = TelegramWebAppUser(
        id=telegram_id,
        username=user_obj.get("username"),
        language_code=user_obj.get("language_code"),
        first_name=user_obj.get("first_name"),
        last_name=user_obj.get("last_name"),
        is_premium=user_obj.get("is_premium"),
        allows_write_to_pm=user_obj.get("allows_write_to_pm"),
    )

    return ValidatedInitData(
        user=user,
        auth_date=auth_date,
        raw_hash=received_hash,
        init_data_hash=hash_init_data(init_data),
        query_id=pairs.get("query_id"),
    )
