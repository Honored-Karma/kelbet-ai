"""Privacy-first optional Sentry initialization."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from threading import Lock
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from sentry_sdk.types import Event

from kelbet.config import Settings
from kelbet.observability.context import get_correlation_id

logger = logging.getLogger(__name__)

_SENSITIVE_PARTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "prompt",
    "content",
    "message",
    "initdata",
    "init_data",
    "file",
    "body",
    "response",
    "email",
    "phone",
    "username",
)
_SENSITIVE_EXACT = frozenset({"email", "phone", "username", "name", "full_name"})
_BEARER_RE = re.compile(r"(?i)Bearer\s+\S+")
_INIT_DATA_RE = re.compile(r"(?i)(?:init_?data)=([^\s&]+)")
_INITIALIZE_LOCK = Lock()
_INITIALIZED_SIGNATURE: tuple[object, ...] | None = None


def _sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_EXACT or any(part in normalized for part in _SENSITIVE_PARTS)


def _safe_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _INIT_DATA_RE.sub("init_data=[REDACTED]", value)


def _scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _sensitive_key(key) else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    if isinstance(value, bytes):
        return "[REDACTED]"
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _url_without_query(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def before_send(event: Event, _hint: dict[str, Any]) -> Event:
    """Strip request bodies, credentials, provider payloads and PII before transport."""
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        event_extra = event.get("extra")
        if not isinstance(event_extra, dict):
            event_extra = {}
        event_extra["correlation_id"] = correlation_id
        event["extra"] = event_extra
    cleaned = cast(dict[str, Any], _scrub(dict(event)))

    request = cleaned.get("request")
    if isinstance(request, dict):
        cleaned["request"] = {
            "method": request.get("method"),
            "url": _url_without_query(request.get("url")),
        }
    cleaned.pop("user", None)
    cleaned.pop("server_name", None)
    cleaned.pop("modules", None)
    cleaned.pop("fingerprint", None)
    cleaned.pop("attachments", None)

    safe_extra_keys = {
        "correlation_id",
        "generation_id",
        "provider",
        "model",
        "status",
        "error_code",
        "component",
    }
    extra = cleaned.get("extra")
    if isinstance(extra, dict):
        cleaned["extra"] = {key: value for key, value in extra.items() if key in safe_extra_keys}

    tags = cleaned.get("tags")
    if isinstance(tags, dict):
        cleaned["tags"] = {key: value for key, value in tags.items() if key in safe_extra_keys}

    contexts = cleaned.get("contexts")
    if isinstance(contexts, dict):
        allowed_contexts = {"app", "os", "runtime", "trace"}
        cleaned["contexts"] = {
            key: value for key, value in contexts.items() if key in allowed_contexts
        }

    exception = cleaned.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and "value" in item:
                    item["value"] = "[REDACTED]"
                if isinstance(item, dict):
                    stacktrace = item.get("stacktrace")
                    if isinstance(stacktrace, dict) and isinstance(stacktrace.get("frames"), list):
                        for frame in stacktrace["frames"]:
                            if isinstance(frame, dict):
                                frame.pop("vars", None)
    if "logentry" in cleaned:
        cleaned["logentry"] = {"message": "[REDACTED]"}
    if "message" in cleaned:
        cleaned["message"] = "[REDACTED]"
    breadcrumbs = cleaned.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        for crumb in breadcrumbs["values"]:
            if isinstance(crumb, dict):
                crumb.pop("message", None)
                data = crumb.get("data")
                if isinstance(data, dict):
                    safe_breadcrumb_keys = {
                        "provider",
                        "model",
                        "status",
                        "error_code",
                        "http.method",
                        "http.status_code",
                    }
                    crumb["data"] = {
                        key: value for key, value in data.items() if key in safe_breadcrumb_keys
                    }
                else:
                    crumb.pop("data", None)
    return cast(Event, cleaned)


def initialize_sentry(settings: Settings, *, component: str) -> bool:
    """Initialize Sentry once per process; remain inert unless explicitly enabled."""
    if not settings.sentry_enabled:
        return False
    if not settings.sentry_dsn.strip():
        logger.warning("sentry_disabled_missing_dsn", extra={"component": component})
        return False

    environment = settings.sentry_environment.strip() or settings.app_env
    release = settings.sentry_release.strip() or None
    signature = (
        settings.sentry_dsn,
        environment,
        release,
        settings.sentry_error_sample_rate,
        settings.sentry_traces_sample_rate,
        component,
    )
    global _INITIALIZED_SIGNATURE
    with _INITIALIZE_LOCK:
        if signature == _INITIALIZED_SIGNATURE:
            return True
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=environment,
            release=release,
            sample_rate=settings.sentry_error_sample_rate,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
            max_request_body_size="never",
            before_send=before_send,
            before_send_transaction=before_send,
            include_local_variables=False,
        )
        sentry_sdk.set_tag("component", component)
        _INITIALIZED_SIGNATURE = signature
        return True


def reset_sentry_state_for_tests() -> None:
    global _INITIALIZED_SIGNATURE
    with _INITIALIZE_LOCK:
        _INITIALIZED_SIGNATURE = None
