from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import sentry_sdk
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient

from kelbet.config import Settings, get_settings
from kelbet.observability import (
    METRIC_SPECS,
    JsonFormatter,
    NoopMetrics,
    PrometheusMetrics,
    before_send,
    get_metrics,
    initialize_observability,
    redact_mapping,
)
from kelbet.observability.sentry import initialize_sentry, reset_sentry_state_for_tests


def test_redact_mapping_strips_secrets() -> None:
    data = {
        "prompt": "secret user text",
        "authorization": "Bearer abc.def",
        "provider": "mock",
        "nested": {"access_token": "xyz", "ok": 1},
        "values": ["Bearer another.secret"],
    }
    redacted = redact_mapping(data)
    assert redacted["prompt"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["provider"] == "mock"
    assert redacted["nested"]["access_token"] == "[REDACTED]"
    assert redacted["nested"]["ok"] == 1
    assert redacted["values"] == ["Bearer [REDACTED]"]


def test_json_formatter_includes_correlation_and_redacts_token() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request Authorization: Bearer super-secret",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "cid-1"
    record.provider = "mock"
    line = JsonFormatter().format(record)
    assert '"correlation_id": "cid-1"' in line
    assert '"provider": "mock"' in line
    assert "super-secret" not in line
    assert "Bearer [REDACTED]" in line


def test_observability_disabled_configuration_is_inert() -> None:
    state = initialize_observability(
        Settings(sentry_enabled=False, metrics_enabled=False),
        component="api",
        force=True,
    )
    assert isinstance(state.metrics, NoopMetrics)
    assert state.sentry_enabled is False
    assert isinstance(get_metrics(), NoopMetrics)


def test_prometheus_backend_exports_bounded_metrics() -> None:
    metrics = PrometheusMetrics(component="api")
    for name, spec in METRIC_SPECS.items():
        tags = {label: sorted(values)[0] for label, values in spec.label_values.items()}
        if spec.kind == "counter":
            metrics.incr(name, tags=tags)
        else:
            metrics.observe(name, 1.0, tags=tags)
    metrics.incr(
        "generation.created",
        tags={"modality": "image", "provider": "unexpected-provider"},
    )
    metrics.incr(
        "provider.failure",
        tags={"provider": "runway", "classification": "timeout"},
    )
    metrics.observe(
        "generation.duration_seconds",
        12.5,
        tags={"status": "succeeded", "modality": "image", "provider": "runway"},
    )
    exported = metrics.export().decode()
    assert "kelbet_generation_created_total" in exported
    assert 'provider="other"' in exported
    assert "kelbet_provider_failures_total" in exported
    assert "kelbet_generation_duration_seconds_bucket" in exported
    for spec in METRIC_SPECS.values():
        assert spec.export_name in exported


def test_metric_catalog_forbids_high_cardinality_labels() -> None:
    forbidden = {
        "user_id",
        "generation_id",
        "correlation_id",
        "prompt",
        "error_message",
    }
    for spec in METRIC_SPECS.values():
        assert forbidden.isdisjoint(spec.label_values)

    metrics = PrometheusMetrics(component="worker")
    with pytest.raises(ValueError, match="sensitive metric labels"):
        metrics.incr(
            "generation.created",
            tags={"modality": "image", "provider": "runway", "user_id": "123"},
        )


def test_sentry_before_send_removes_secrets_payloads_and_pii() -> None:
    event = cast(
        Any,
        {
            "message": "provider failed for user@example.com",
            "user": {"id": "42", "email": "user@example.com", "username": "private"},
            "request": {
                "method": "POST",
                "url": "https://api.example.test/generate?initData=secret-init-data",
                "headers": {"Authorization": "Bearer secret-token", "Cookie": "session=1"},
                "data": {"prompt": "private prompt", "file_contents": b"private bytes"},
            },
            "extra": {
                "correlation_id": "safe-correlation",
                "provider_response": {"body": "private provider body"},
                "raw_payload": "private payload",
            },
            "tags": {"component": "worker", "username": "private-user"},
            "exception": {
                "values": [
                    {
                        "type": "ProviderError",
                        "value": "private provider response",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "runner.py",
                                    "lineno": 1,
                                    "vars": {"value": "private local value"},
                                }
                            ]
                        },
                    }
                ]
            },
            "breadcrumbs": {
                "values": [
                    {
                        "message": "private prompt",
                        "data": {"provider_response": "private provider response"},
                    }
                ]
            },
        },
    )
    cleaned = before_send(event, {})
    serialized = json.dumps(cleaned, default=str)
    for secret in (
        "secret-init-data",
        "secret-token",
        "private prompt",
        "private bytes",
        "private provider response",
        "private local value",
        "private-user",
        "user@example.com",
    ):
        assert secret not in serialized
    assert "user" not in cleaned
    assert cleaned["request"] == {
        "method": "POST",
        "url": "https://api.example.test/generate",
    }
    assert cleaned["extra"] == {"correlation_id": "safe-correlation"}
    assert cleaned["tags"] == {"component": "worker"}
    assert cleaned["exception"]["values"][0]["value"] == "[REDACTED]"


def test_sentry_initialization_is_safe_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    tags: list[tuple[str, str]] = []

    def fake_init(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(sentry_sdk, "init", fake_init)
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda key, value: tags.append((key, value)))
    reset_sentry_state_for_tests()
    settings = Settings(
        sentry_enabled=True,
        sentry_dsn="https://public@example.invalid/1",
        sentry_environment="staging",
        sentry_release="test-sha",
        sentry_traces_sample_rate=0.1,
    )
    assert initialize_sentry(settings, component="worker") is True
    assert initialize_sentry(settings, component="worker") is True
    assert len(calls) == 1
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["max_request_body_size"] == "never"
    assert calls[0]["before_send"] is before_send
    assert calls[0]["include_local_variables"] is False
    assert tags == [("component", "worker")]


@pytest.mark.asyncio
async def test_metrics_endpoint_is_protected_and_correlation_id_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("METRICS_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "metrics-test-token")
    monkeypatch.setenv("SENTRY_ENABLED", "false")
    get_settings.cache_clear()
    try:
        app = create_app(testing=True)
        get_metrics().incr(
            "generation.created",
            tags={"modality": "image", "provider": "mock"},
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            unauthorized = await client.get("/metrics")
            assert unauthorized.status_code == 401
            assert unauthorized.headers["www-authenticate"] == "Bearer"

            exported = await client.get(
                "/metrics",
                headers={"Authorization": "Bearer metrics-test-token"},
            )
            assert exported.status_code == 200
            assert "kelbet_generation_created_total" in exported.text

            correlation_id = str(uuid4())
            live = await client.get(
                "/health",
                headers={"X-Correlation-ID": correlation_id},
            )
            assert live.status_code == 200
            assert live.headers["X-Correlation-ID"] == correlation_id

            invalid = await client.get(
                "/health",
                headers={"X-Correlation-ID": "not-a-uuid"},
            )
            assert UUID(invalid.headers["X-Correlation-ID"])
            assert invalid.headers["X-Correlation-ID"] != "not-a-uuid"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_metrics_endpoint_is_not_discoverable_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("METRICS_ENDPOINT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        app = create_app(testing=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")
            assert response.status_code == 404
            assert (await client.get("/health")).json() == {"status": "ok"}
            app.state.readiness_require_redis = True
            readiness = await client.get("/api/v1/ready")
            assert readiness.status_code == 503
            assert readiness.json()["checks"] == {
                "database": "missing",
                "redis": "missing",
            }
    finally:
        get_settings.cache_clear()
