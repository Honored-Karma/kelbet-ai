# Observability incident runbook

This runbook covers alerts emitted from KELBET metrics and Sentry. It does not authorize deleting
data, manually changing wallet balances, replaying payment receipts or exposing prompts/provider
responses. Prefer a feature flag, provider disablement or a compensating wallet operation.

## First five minutes

1. Acknowledge the alert and record its start time, environment, release and affected component.
2. Compare `/health` with `/api/v1/ready`. A live-but-not-ready API usually points to PostgreSQL or
   Redis, not a process crash.
3. Check the latest deploy and Sentry issue by correlation ID/error code. Never paste a bearer
   token, Telegram initData, prompt, file, provider payload or payment charge ID into the incident
   channel.
4. Determine blast radius: modality/provider, worker queue, wallet operation or payment receipt.
5. If money or irreversible provider spend is at risk, stop the affected feature/provider before
   attempting recovery.

## Readiness failure

- `database=error|missing`: inspect Railway PostgreSQL state, connection limits and the last
  migration. Do not repeatedly restart while a migration is active.
- `redis=error|missing`: inspect Redis connectivity and memory. Generation creation should be
  paused if the production queue/replay protection cannot reach Redis.
- If only `/health` succeeds, keep the service out of traffic until `/api/v1/ready` is consistently
  `200` for five minutes.

## Generation or provider failures

1. Group by bounded `provider`, `modality` and `classification`; do not add raw error text as a
   metric label.
2. For `authentication`, verify sealed key presence and provider account status without printing
   the key. For `rate_limit`, reduce concurrency or disable the route. For `timeout/upstream`, check
   provider status and the fallback policy.
3. Confirm failed/timed-out jobs released their reservation. Successful jobs must have exactly one
   capture.
4. Disable the affected provider/model through the existing configuration/catalog control when the
   error ratio remains elevated.

## Stuck generations

1. Inspect status, timestamps, reservation state and provider job ID using internal operator tools.
2. Verify the sweeper attempted provider cancellation and moved the job to `timed_out`.
3. Verify a held reservation was released. Do not refund a captured reservation until delivery is
   known; use the compensation rules in `GENERATION_STATE_MACHINE.md`.
4. Check worker restart loops, queue connectivity and provider polling latency before replaying any
   job.

## Payment rejection

1. Group by the bounded rejection reason. Never share invoice payloads or Telegram/provider charge
   IDs outside the restricted operator channel.
2. Confirm the immutable receipt exists and remains `rejected`; do not delete or mutate the receipt
   to force a retry.
3. Check currency, amount, buyer mapping and whether the order was already paid.
4. If a paid Telegram charge lacks a ledger transaction, stop payments and escalate for explicit
   reconciliation. Do not grant credits manually through SQL.

## Worker failure

1. Identify the bounded queue/job label and compare with Sentry for the same release and correlation
   ID.
2. Check Redis, database and object storage connectivity; then check provider availability.
3. Confirm ARQ stopped dequeueing cleanly during deploy and that the maintain worker still runs.
4. After recovery, verify queue activity, stuck sweeps and terminal generation rates return to the
   baseline.

## Recovery and closure

- Observe readiness and the triggering metric for at least 15 minutes.
- Check wallet conservation for affected generations/payments.
- Record timeline, root cause, affected IDs in the restricted system, mitigation, rollback and
  follow-up owner.
- Rotate any secret that may have appeared in a repository, log, Sentry event or incident message.
- A staging alert drill and real notification delivery remain required before declaring production
  alerting operational.
