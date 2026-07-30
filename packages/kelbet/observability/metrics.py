"""Noop metrics protocol — naming in docs/architecture/METRICS.md."""

from __future__ import annotations

from typing import Protocol


class Metrics(Protocol):
    def incr(self, name: str, *, value: int = 1, tags: dict[str, str] | None = None) -> None: ...

    def observe(
        self, name: str, value: float, *, tags: dict[str, str] | None = None
    ) -> None: ...


class NoopMetrics:
    def incr(self, name: str, *, value: int = 1, tags: dict[str, str] | None = None) -> None:
        return None

    def observe(
        self, name: str, value: float, *, tags: dict[str, str] | None = None
    ) -> None:
        return None


_METRICS: Metrics = NoopMetrics()


def get_metrics() -> Metrics:
    return _METRICS


def set_metrics(metrics: Metrics) -> None:
    global _METRICS
    _METRICS = metrics
