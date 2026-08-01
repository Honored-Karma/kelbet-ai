"""Shared idempotent observability bootstrap for API, bot and worker processes."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal

from kelbet.config import Settings
from kelbet.observability.logging import configure_json_logging
from kelbet.observability.metrics import Metrics, NoopMetrics, PrometheusMetrics, set_metrics
from kelbet.observability.sentry import initialize_sentry

Component = Literal["api", "bot", "worker"]


@dataclass(frozen=True, slots=True)
class ObservabilityState:
    component: Component
    metrics: Metrics
    sentry_enabled: bool


_LOCK = Lock()
_SIGNATURE: tuple[object, ...] | None = None
_STATE: ObservabilityState | None = None


def initialize_observability(
    settings: Settings,
    *,
    component: Component,
    force: bool = False,
) -> ObservabilityState:
    """Configure logging, metrics and Sentry once, with a deterministic test override."""
    configure_json_logging(settings.log_level)
    signature = (
        component,
        settings.log_level.upper(),
        settings.metrics_enabled,
        settings.sentry_enabled,
        settings.sentry_dsn,
        settings.sentry_environment,
        settings.sentry_release,
        settings.sentry_error_sample_rate,
        settings.sentry_traces_sample_rate,
    )
    global _SIGNATURE, _STATE
    with _LOCK:
        if not force and signature == _SIGNATURE and _STATE is not None:
            return _STATE
        metrics: Metrics
        if settings.metrics_enabled:
            metrics = PrometheusMetrics(component=component)
        else:
            metrics = NoopMetrics()
        set_metrics(metrics)
        sentry_active = initialize_sentry(settings, component=component)
        _STATE = ObservabilityState(
            component=component,
            metrics=metrics,
            sentry_enabled=sentry_active,
        )
        _SIGNATURE = signature
        return _STATE
