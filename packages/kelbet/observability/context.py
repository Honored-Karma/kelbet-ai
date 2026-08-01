"""Process-local observability context shared by logging and error reporting."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_CORRELATION_ID: ContextVar[str | None] = ContextVar("kelbet_correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()


def set_correlation_id(value: str) -> Token[str | None]:
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    _CORRELATION_ID.reset(token)


@contextmanager
def correlation_context(value: str) -> Iterator[None]:
    token = set_correlation_id(value)
    try:
        yield
    finally:
        reset_correlation_id(token)
