"""Bounded Prometheus metrics behind the application metrics protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client.exposition import generate_latest


class Metrics(Protocol):
    def incr(self, name: str, *, value: int = 1, tags: dict[str, str] | None = None) -> None: ...

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None: ...


class NoopMetrics:
    def incr(self, name: str, *, value: int = 1, tags: dict[str, str] | None = None) -> None:
        return None

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        return None


@dataclass(frozen=True, slots=True)
class MetricSpec:
    export_name: str
    help: str
    kind: Literal["counter", "histogram"]
    label_values: dict[str, frozenset[str]]
    buckets: tuple[float, ...] = ()


_MODALITIES = frozenset({"text", "image", "image_edit", "video", "upscale", "other"})
_PROVIDERS = frozenset(
    {"mock", "runway", "google", "google_veo", "openrouter", "rules", "openai", "off", "other"}
)
_GENERATION_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "timed_out", "dead_letter", "other"}
)
_OUTCOMES = frozenset(
    {
        "applied",
        "idempotent",
        "rejected",
        "failed",
        "started",
        "succeeded",
        "empty",
        "skipped",
        "other",
    }
)
_TEMPLATES = frozenset(
    {
        "marketplace-product",
        "cafe-promo",
        "local-service-story",
        "kazakh-fashion",
        "real-estate",
        "nauryz",
        "kaspi-reveal",
        "cafe-menu",
        "property",
        "toi",
        "social-hook",
        "other",
    }
)
_TEMPLATE_KINDS = frozenset({"image", "video", "other"})

METRIC_SPECS: dict[str, MetricSpec] = {
    "generation.created": MetricSpec(
        "kelbet_generation_created_total",
        "Generation jobs created.",
        "counter",
        {"modality": _MODALITIES, "provider": _PROVIDERS},
    ),
    "generation.terminal": MetricSpec(
        "kelbet_generation_terminal_total",
        "Generation jobs entering a terminal state.",
        "counter",
        {"status": _GENERATION_STATUSES, "modality": _MODALITIES},
    ),
    "generation.duration_seconds": MetricSpec(
        "kelbet_generation_duration_seconds",
        "End-to-end generation duration in seconds.",
        "histogram",
        {"status": _GENERATION_STATUSES, "modality": _MODALITIES, "provider": _PROVIDERS},
        (1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600),
    ),
    "provider.failure": MetricSpec(
        "kelbet_provider_failures_total",
        "Provider failures grouped into a bounded safe classification.",
        "counter",
        {
            "provider": _PROVIDERS,
            "classification": frozenset(
                {
                    "timeout",
                    "authentication",
                    "rate_limit",
                    "validation",
                    "upstream",
                    "cancelled",
                    "unknown",
                    "other",
                }
            ),
        },
    ),
    "provider.route": MetricSpec(
        "kelbet_provider_route_total",
        "Primary and fallback provider route outcomes.",
        "counter",
        {
            "provider": _PROVIDERS,
            "route": frozenset({"primary", "fallback", "other"}),
            "outcome": frozenset({"succeeded", "failed", "other"}),
            "modality": _MODALITIES,
        },
    ),
    "provider.route_latency_seconds": MetricSpec(
        "kelbet_provider_route_latency_seconds",
        "Provider attempt latency split by primary and fallback route.",
        "histogram",
        {
            "provider": _PROVIDERS,
            "route": frozenset({"primary", "fallback", "other"}),
            "outcome": frozenset({"succeeded", "failed", "other"}),
            "modality": _MODALITIES,
        },
        (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 30, 60, 120, 300, 600),
    ),
    "provider.route_cost_units": MetricSpec(
        "kelbet_provider_route_cost_units",
        "Provider cost units split by primary and fallback route.",
        "histogram",
        {
            "provider": _PROVIDERS,
            "route": frozenset({"primary", "fallback", "other"}),
            "modality": _MODALITIES,
        },
        (0, 50, 100, 250, 450, 670, 1010, 1510, 2500, 5000, 10000, 25000),
    ),
    "wallet.operation": MetricSpec(
        "kelbet_wallet_operations_total",
        "Wallet reservation and compensation operations.",
        "counter",
        {
            "operation": frozenset(
                {"reserve", "capture", "release", "refund", "credit", "debit", "other"}
            ),
            "outcome": _OUTCOMES,
        },
    ),
    "stuck_generation.total": MetricSpec(
        "kelbet_stuck_generations_total",
        "Stuck generation recovery actions.",
        "counter",
        {
            "action": frozenset({"timed_out", "cancel_failed", "other"}),
            "modality": _MODALITIES,
            "previous_status": frozenset({"submitting", "running", "finalizing", "other"}),
        },
    ),
    "payment.receipt": MetricSpec(
        "kelbet_payment_receipts_total",
        "Telegram Stars payment receipts by processing result.",
        "counter",
        {"status": frozenset({"processed", "rejected", "duplicate", "other"})},
    ),
    "payment.rejected": MetricSpec(
        "kelbet_payment_rejected_total",
        "Rejected Telegram Stars payments by bounded reason.",
        "counter",
        {
            "reason": frozenset(
                {
                    "payments_unavailable",
                    "order_not_found",
                    "buyer_mismatch",
                    "currency_mismatch",
                    "amount_mismatch",
                    "order_not_payable",
                    "order_expired",
                    "order_already_paid",
                    "pre_checkout_already_claimed",
                    "duplicate_order_charge_refund_required",
                    "other",
                }
            )
        },
    ),
    "payment.pre_checkout_duration_seconds": MetricSpec(
        "kelbet_payment_pre_checkout_duration_seconds",
        "Telegram Stars pre-checkout handling duration in seconds.",
        "histogram",
        {"outcome": frozenset({"approved", "rejected", "timeout", "error", "other"})},
        (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 6, 8),
    ),
    "payment.refund": MetricSpec(
        "kelbet_payment_refunds_total",
        "Telegram Stars refund state transitions.",
        "counter",
        {
            "status": frozenset(
                {"requested", "processing", "refunded", "failed", "needs_review", "other"}
            )
        },
    ),
    "payment.reconciliation": MetricSpec(
        "kelbet_payment_reconciliation_runs_total",
        "Telegram Stars reconciliation outcomes.",
        "counter",
        {"outcome": frozenset({"clean", "issues", "failed", "disabled", "other"})},
    ),
    "payment.reconciliation_issue": MetricSpec(
        "kelbet_payment_reconciliation_issues_total",
        "Telegram Stars discrepancies by bounded class.",
        "counter",
        {
            "kind": frozenset(
                {
                    "telegram_without_receipt",
                    "paid_without_ledger",
                    "ledger_without_transaction",
                    "refund_without_reverse_ledger",
                    "duplicate_charge_id",
                    "external_reversal",
                    "transaction_amount_mismatch",
                    "other",
                }
            )
        },
    ),
    "referral.funnel": MetricSpec(
        "kelbet_referral_funnel_total",
        "Referral attribution, first-purchase and reward outcomes.",
        "counter",
        {
            "stage": frozenset({"attribution", "first_purchase", "reward", "reversal", "other"}),
            "outcome": frozenset(
                {
                    "created",
                    "disabled",
                    "invalid",
                    "unknown",
                    "self",
                    "existing",
                    "race_replay",
                    "eligible",
                    "below_minimum",
                    "credited",
                    "cancelled",
                    "needs_review",
                    "daily_limited",
                    "other",
                }
            ),
        },
    ),
    "worker.job": MetricSpec(
        "kelbet_worker_jobs_total",
        "Worker job executions by bounded queue, function and outcome.",
        "counter",
        {
            "queue": frozenset({"image", "text", "video", "maintain", "other"}),
            "job": frozenset(
                {
                    "process_generation",
                    "poll_due_generations",
                    "sweep_stuck_generations",
                    "dispatch_generation_notifications",
                    "process_star_refund",
                    "reconcile_star_transactions",
                    "process_referral_rewards",
                    "other",
                }
            ),
            "outcome": _OUTCOMES,
        },
    ),
    "worker.job_duration_seconds": MetricSpec(
        "kelbet_worker_job_duration_seconds",
        "Worker job execution duration in seconds.",
        "histogram",
        {
            "queue": frozenset({"image", "text", "video", "maintain", "other"}),
            "job": frozenset(
                {
                    "process_generation",
                    "poll_due_generations",
                    "sweep_stuck_generations",
                    "dispatch_generation_notifications",
                    "process_star_refund",
                    "reconcile_star_transactions",
                    "process_referral_rewards",
                    "other",
                }
            ),
            "outcome": _OUTCOMES,
        },
        (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 30, 60, 300, 900),
    ),
    "moderation.decision": MetricSpec(
        "kelbet_moderation_decisions_total",
        "Privacy-safe moderation decisions by bounded context, outcome and provider.",
        "counter",
        {
            "outcome": frozenset({"allow", "report", "block", "other"}),
            "context": frozenset({"generation", "chat", "prompt_assistant", "other"}),
            "provider": _PROVIDERS,
        },
    ),
    "template.selected": MetricSpec(
        "kelbet_template_selected_total",
        "Server-side generation template selections.",
        "counter",
        {"template": _TEMPLATES, "kind": _TEMPLATE_KINDS},
    ),
    "template.started": MetricSpec(
        "kelbet_template_started_total",
        "Generation jobs started from a server-side template.",
        "counter",
        {"template": _TEMPLATES, "kind": _TEMPLATE_KINDS},
    ),
    "template.terminal": MetricSpec(
        "kelbet_template_terminal_total",
        "Template generation jobs reaching success or failure.",
        "counter",
        {
            "template": _TEMPLATES,
            "kind": _TEMPLATE_KINDS,
            "outcome": frozenset({"succeeded", "failed", "other"}),
        },
    ),
    "template.reused": MetricSpec(
        "kelbet_template_reused_total",
        "Template snapshots restored into a new draft.",
        "counter",
        {"template": _TEMPLATES, "kind": _TEMPLATE_KINDS},
    ),
}

_FORBIDDEN_LABELS = frozenset(
    {
        "user_id",
        "generation_id",
        "correlation_id",
        "prompt",
        "message",
        "error",
        "error_message",
        "provider_job_id",
        "payment_order_id",
        "receipt_id",
    }
)


class PrometheusMetrics:
    """Prometheus client backend with a fixed schema and bounded label values."""

    content_type = CONTENT_TYPE_LATEST

    def __init__(
        self,
        *,
        component: Literal["api", "bot", "worker"],
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._component = component
        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._collectors: dict[str, Counter | Histogram] = {}
        for public_name, spec in METRIC_SPECS.items():
            labels = ("component", *spec.label_values)
            if spec.kind == "counter":
                collector: Counter | Histogram = Counter(
                    spec.export_name,
                    spec.help,
                    labels,
                    registry=self._registry,
                )
            else:
                collector = Histogram(
                    spec.export_name,
                    spec.help,
                    labels,
                    buckets=spec.buckets,
                    registry=self._registry,
                )
            self._collectors[public_name] = collector

    @property
    def registry(self) -> CollectorRegistry:
        return self._registry

    def _labels(self, name: str, tags: dict[str, str] | None) -> dict[str, str]:
        spec = METRIC_SPECS.get(name)
        if spec is None:
            raise ValueError(f"Unknown metric: {name}")
        raw_tags = tags or {}
        forbidden = set(raw_tags) & _FORBIDDEN_LABELS
        if forbidden:
            raise ValueError(
                f"High-cardinality or sensitive metric labels are forbidden: {forbidden}"
            )
        expected = set(spec.label_values)
        if set(raw_tags) != expected:
            raise ValueError(f"Metric {name} requires labels {sorted(expected)}")
        labels: dict[str, str] = {"component": self._component}
        for key, allowed in spec.label_values.items():
            normalized = str(raw_tags[key]).strip().lower().replace("-", "_")
            labels[key] = normalized if normalized in allowed else "other"
        return labels

    def incr(self, name: str, *, value: int = 1, tags: dict[str, str] | None = None) -> None:
        spec = METRIC_SPECS.get(name)
        if spec is None or spec.kind != "counter":
            raise ValueError(f"Metric {name} is not a counter")
        collector = self._collectors[name]
        assert isinstance(collector, Counter)
        collector.labels(**self._labels(name, tags)).inc(value)

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        spec = METRIC_SPECS.get(name)
        if spec is None or spec.kind != "histogram":
            raise ValueError(f"Metric {name} is not a histogram")
        collector = self._collectors[name]
        assert isinstance(collector, Histogram)
        collector.labels(**self._labels(name, tags)).observe(value)

    def export(self) -> bytes:
        return generate_latest(self._registry)


def classify_provider_failure(error_code: str | None, http_status: int | None = None) -> str:
    """Map internal/provider errors to a small, non-sensitive classification."""
    code = (error_code or "").strip().lower()
    if code == "provider_unsupported":
        return "configuration"
    if "timeout" in code:
        return "timeout"
    if http_status in {401, 403} or code in {"unauthorized", "authentication_failed"}:
        return "authentication"
    if http_status == 429 or code in {"rate_limited", "quota_exceeded"}:
        return "rate_limit"
    if http_status is not None and 400 <= http_status < 500:
        return "validation"
    if http_status is not None and http_status >= 500:
        return "upstream"
    if code in {"provider_unavailable", "provider_http_error", "provider_failed"}:
        return "upstream"
    if "cancel" in code:
        return "cancelled"
    return "unknown"


_METRICS: Metrics = NoopMetrics()


def get_metrics() -> Metrics:
    return _METRICS


def set_metrics(metrics: Metrics) -> None:
    global _METRICS
    _METRICS = metrics


def export_metrics() -> tuple[bytes, str] | None:
    metrics = get_metrics()
    if not isinstance(metrics, PrometheusMetrics):
        return None
    return metrics.export(), metrics.content_type
