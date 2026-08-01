# Observability: metrics, labels and dashboards

KELBET uses one observability bootstrap in API, bot and worker processes. The default is
deliberately inert: `SENTRY_ENABLED=false`, `METRICS_ENABLED=false` and
`METRICS_ENDPOINT_ENABLED=false`.

The Prometheus backend is implemented by `PrometheusMetrics` behind the existing `Metrics`
protocol. It owns a process-local registry, uses a fixed metric catalogue and rejects unexpected
or sensitive labels. The API exposes that registry at `/metrics` only when both metrics flags are
enabled and a dedicated bearer token is configured.

## Configuration

| Variable | Default | Meaning |
|---|---:|---|
| `SENTRY_ENABLED` | `false` | Enable Sentry initialization in the current process. |
| `SENTRY_DSN` | empty | Secret DSN, stored only in the deployment environment. |
| `SENTRY_ENVIRONMENT` | `APP_ENV` | Environment tag such as `staging` or `production`. |
| `SENTRY_RELEASE` | empty | Immutable release identifier, normally the Git SHA. |
| `SENTRY_ERROR_SAMPLE_RATE` | `1.0` | Error event sample rate, from `0` to `1`. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Trace sample rate, from `0` to `1`. |
| `METRICS_ENABLED` | `false` | Install the Prometheus backend instead of `NoopMetrics`. |
| `METRICS_ENDPOINT_ENABLED` | `false` | Publish the API `/metrics` route. |
| `METRICS_BEARER_TOKEN` | empty | Independent high-entropy token required by `/metrics`. |
| `READINESS_REQUIRE_REDIS` | `true` | Treat missing Redis as a readiness failure outside tests. |

Never reuse `BOT_TOKEN`, a session token, provider key or webhook secret as the metrics token.
Generate at least 32 random bytes and store it as a sealed deployment variable.

## Exported series

Every series has the bounded `component` label: `api`, `bot` or `worker`.

| Application name | Prometheus series | Type | Labels |
|---|---|---|---|
| `generation.created` | `kelbet_generation_created_total` | counter | `modality`, `provider` |
| `generation.terminal` | `kelbet_generation_terminal_total` | counter | `status`, `modality` |
| `generation.duration_seconds` | `kelbet_generation_duration_seconds` | histogram | `status`, `modality`, `provider` |
| `provider.failure` | `kelbet_provider_failures_total` | counter | `provider`, `classification` |
| `provider.route` | `kelbet_provider_route_total` | counter | `provider`, `route`, `outcome`, `modality` |
| `provider.route_latency_seconds` | `kelbet_provider_route_latency_seconds` | histogram | `provider`, `route`, `outcome`, `modality` |
| `provider.route_cost_units` | `kelbet_provider_route_cost_units` | histogram | `provider`, `route`, `modality` |
| `wallet.operation` | `kelbet_wallet_operations_total` | counter | `operation`, `outcome` |
| `stuck_generation.total` | `kelbet_stuck_generations_total` | counter | `action`, `modality`, `previous_status` |
| `payment.receipt` | `kelbet_payment_receipts_total` | counter | `status` |
| `payment.rejected` | `kelbet_payment_rejected_total` | counter | `reason` |
| `payment.refund` | `kelbet_payment_refunds_total` | counter | `status` |
| `payment.reconciliation` | `kelbet_payment_reconciliation_runs_total` | counter | `outcome` |
| `payment.reconciliation_issue` | `kelbet_payment_reconciliation_issues_total` | counter | `kind` |
| `worker.job` | `kelbet_worker_jobs_total` | counter | `queue`, `job`, `outcome` |
| `worker.job_duration_seconds` | `kelbet_worker_job_duration_seconds` | histogram | `queue`, `job`, `outcome` |
| `moderation.decision` | `kelbet_moderation_decisions_total` | counter | `outcome`, `context`, `provider` |
| `template.selected` | `kelbet_template_selected_total` | counter | `template`, `kind` |
| `template.started` | `kelbet_template_started_total` | counter | `template`, `kind` |
| `template.terminal` | `kelbet_template_terminal_total` | counter | `template`, `kind`, `outcome` |
| `template.reused` | `kelbet_template_reused_total` | counter | `template`, `kind` |
| `referral.funnel` | `kelbet_referral_funnel_total` | counter | `stage`, `outcome` |

Unknown label values become `other`. Unknown label names, missing labels and metric names outside the
catalogue fail immediately. User IDs, generation IDs, correlation IDs, prompts, provider job IDs,
payment/order IDs and error messages are forbidden as labels.

Provider errors are reduced to one of `timeout`, `authentication`, `rate_limit`, `validation`,
`upstream`, `cancelled` or `unknown`. The original provider response and exception message never
become labels.

## Endpoint contract

- `GET /health` is liveness only and does not call PostgreSQL or Redis.
- `GET /api/v1/ready` checks PostgreSQL and required Redis; failure returns `503`.
- `GET /metrics` returns `404` when disabled, `503` when enabled but misconfigured, `401` for a
  missing/invalid bearer credential, and Prometheus text for valid credentials.
- The endpoint is excluded from OpenAPI and sends `Cache-Control: no-store`.

Example scrape header:

```text
Authorization: Bearer <METRICS_BEARER_TOKEN>
```

## Dashboard panels

Recommended minimum panels:

1. Generation terminal rate grouped by `status` and `modality`.
2. Generation p50/p95 duration from `kelbet_generation_duration_seconds_bucket`.
3. Provider failures grouped by `provider` and safe `classification`.
4. Wallet operation outcomes grouped by `operation`.
5. Payment receipts and rejection reasons.
6. Stuck-generation recovery actions.
7. Worker job rate, failure rate and p95 duration by queue/job.
8. Moderation `allow/report/block` rate by context and bounded provider name.
9. Template selection-to-start conversion and success/failure rate by bounded server slug.
10. Stars refund state transitions, reconciliation outcomes and discrepancy classes.
11. Primary/fallback success, latency and provider cost by bounded provider and modality.
12. Referral attribution → first purchase → reward conversion, daily-limit postponements,
    cancellations and `needs_review` outcomes by bounded stage/outcome only.

Prometheus registries are process-local. In a multi-service deployment, configure the monitoring
platform to scrape each exposed process endpoint or ingest each process registry. Do not infer
worker/bot health from the API registry alone.

Alert rules live in `deploy/observability/prometheus-alerts.yml`; response steps are in
`docs/architecture/OBSERVABILITY_INCIDENT_RUNBOOK.md`.
