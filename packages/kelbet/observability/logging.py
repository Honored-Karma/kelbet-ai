"""Structured JSON logging helpers with sensitive-field redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "correlation_id",
            "generation_id",
            "user_id",
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

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _REDACT_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, str):
            redacted[key] = _BEARER_RE.sub("Bearer [REDACTED]", value)
        else:
            redacted[key] = value
    return redacted


def configure_json_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_extra(**kwargs: Any) -> dict[str, Any]:
    """Build a logging `extra` dict with safe values only."""
    return {k: v for k, v in kwargs.items() if v is not None}
