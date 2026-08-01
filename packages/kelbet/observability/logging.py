"""Structured JSON logging helpers with sensitive-field redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from kelbet.observability.context import get_correlation_id

_REDACT_KEYS = frozenset(
    {
        "prompt",
        "message",
        "content",
        "init_data",
        "initdata",
        "authorization",
        "access_token",
        "token",
        "bot_token",
        "api_key",
        "password",
    }
)

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_INIT_DATA_RE = re.compile(r"(?i)(init_?data)=([^\s&]+)")


def redact_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _BOT_TOKEN_RE.sub("[REDACTED_BOT_TOKEN]", value)
    return _INIT_DATA_RE.sub("init_data=[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key in (
            "correlation_id",
            "generation_id",
            "provider",
            "model",
            "latency_ms",
            "provider_cost_units",
            "user_credit_price",
            "status",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = str(value) if isinstance(value, UUID) else value

        if "correlation_id" not in payload:
            correlation_id = get_correlation_id()
            if correlation_id is not None:
                payload["correlation_id"] = correlation_id

        if record.exc_info:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_type"] = exception_type.__name__

        return json.dumps(payload, ensure_ascii=False, default=str)


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _REDACT_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_mapping(item)
                if isinstance(item, dict)
                else redact_text(item)
                if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = value
    return redacted


def configure_json_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    handler = next(
        (item for item in root.handlers if item.name == "kelbet-json"),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler.set_name("kelbet-json")
        root.addHandler(handler)
    handler.setFormatter(JsonFormatter())
    root.setLevel(level.upper())


def bind_extra(**kwargs: Any) -> dict[str, Any]:
    """Build a logging `extra` dict with safe values only."""
    return {k: v for k, v in kwargs.items() if v is not None}
