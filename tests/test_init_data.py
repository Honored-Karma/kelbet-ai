"""Unit tests for Telegram initData crypto helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from kelbet.auth import sign_init_data, validate_init_data
from kelbet.domain.exceptions import ExpiredInitDataError, InvalidInitDataError

BOT_TOKEN = "123456:ABC-DEF"


def _user_json(*, telegram_id: int = 42, language_code: str = "ru") -> str:
    return json.dumps(
        {
            "id": telegram_id,
            "username": "kelbet_user",
            "language_code": language_code,
            "first_name": "Test",
        },
        separators=(",", ":"),
    )


def test_validate_signed_init_data() -> None:
    auth_date = int(datetime(2026, 7, 30, 0, 0, tzinfo=UTC).timestamp())
    init_data = sign_init_data(
        {
            "auth_date": str(auth_date),
            "user": _user_json(),
            "query_id": "AAE",
        },
        BOT_TOKEN,
    )
    validated = validate_init_data(
        init_data,
        BOT_TOKEN,
        max_age_seconds=10**9,
        now=datetime(2026, 7, 30, 0, 1, tzinfo=UTC),
    )
    assert validated.user.id == 42
    assert validated.user.username == "kelbet_user"


def test_tampered_hash_rejected() -> None:
    auth_date = int(datetime(2026, 7, 30, 0, 0, tzinfo=UTC).timestamp())
    init_data = sign_init_data(
        {"auth_date": str(auth_date), "user": _user_json()},
        BOT_TOKEN,
    )
    tampered = init_data[:-4] + "dead"
    with pytest.raises(InvalidInitDataError):
        validate_init_data(
            tampered,
            BOT_TOKEN,
            max_age_seconds=10**9,
            now=datetime(2026, 7, 30, 0, 1, tzinfo=UTC),
        )


def test_expired_auth_date() -> None:
    auth_date = int(datetime(2026, 7, 1, 0, 0, tzinfo=UTC).timestamp())
    init_data = sign_init_data(
        {"auth_date": str(auth_date), "user": _user_json()},
        BOT_TOKEN,
    )
    with pytest.raises(ExpiredInitDataError):
        validate_init_data(
            init_data,
            BOT_TOKEN,
            max_age_seconds=60,
            now=datetime(2026, 7, 30, 0, 0, tzinfo=UTC),
        )


def test_init_data_unsafe_fields_are_irrelevant() -> None:
    """Server only trusts signed raw initData — client-side unsafe blobs are ignored."""
    auth_date = int(datetime(2026, 7, 30, 0, 0, tzinfo=UTC).timestamp())
    init_data = sign_init_data(
        {"auth_date": str(auth_date), "user": _user_json(telegram_id=7)},
        BOT_TOKEN,
    )
    # Even if a client also sent forged "unsafe" JSON, we never parse it here.
    unsafe = {"id": 999999, "username": "hacker"}
    assert unsafe["id"] != 7
    validated = validate_init_data(
        init_data,
        BOT_TOKEN,
        max_age_seconds=10**9,
        now=datetime(2026, 7, 30, 0, 1, tzinfo=UTC),
    )
    assert validated.user.id == 7
