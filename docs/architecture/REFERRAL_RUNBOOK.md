# Referral MVP — rollout and incident runbook

**Status:** implemented locally in `0017_referral_mvp`; production flag is off.

## Safety contract

- `feature_flags.referrals` is `false` by default and is independent from payment flags.
- Attribution is accepted only for a user created by the current registration transaction.
- The first valid `ref_<code>` touch survives language selection and cannot be replaced later.
- `referral_attributions` cannot be updated or deleted, including by SQL, because migration `0017`
  installs a database trigger.
- A reward becomes eligible only after the incoming Stars transaction is present in normalized
  reconciliation observations and the order is the user's first confirmed, non-reversed purchase.
- Wallet credits use idempotency keys derived from the reward ID. Never edit wallet balances or
  ledger rows manually.
- Reversal before credit cancels the reward. Reversal after credit moves it to `needs_review`;
  there is no automatic negative-balance clawback.

## Configuration

| Variable / flag | Safe default | Meaning |
|---|---:|---|
| DB flag `referrals` | `false` | Master gate for link creation, attribution and rewards. |
| `REFERRAL_BOT_USERNAME` | empty | Bot username used to build the personal deep link. |
| `REFERRAL_INVITER_BONUS_CREDITS` | `5` | Inviter reward snapshot. |
| `REFERRAL_INVITEE_BONUS_CREDITS` | `2` | Invited-user reward snapshot. |
| `REFERRAL_MINIMUM_PURCHASE_STARS` | `50` | Minimum first purchase. |
| `REFERRAL_WAITING_PERIOD_HOURS` | `72` | Delay after reconciled incoming transaction. |
| `REFERRAL_DAILY_REWARD_LIMIT` | `20` | Maximum credited rewards per inviter per UTC day. |
| `REFERRAL_SUSPICIOUS_DAILY_ATTRIBUTION_THRESHOLD` | `50` | Velocity threshold for `needs_review`. |

Changing bonus or limit settings affects only newly created attribution/reward snapshots where
applicable. It must never rewrite existing rows.

## Controlled rollout

1. Apply migrations through `0017_referral_mvp`; verify API and worker are on the same release.
2. Keep `referrals=false`. Confirm Stars reconciliation is enabled, current and free of unresolved
   first-purchase discrepancies.
3. Verify published RU/KK program terms, support ownership and an operator schedule for
   `needs_review` cases.
4. Set a real `REFERRAL_BOT_USERNAME`; verify `/start ref_<code>` and language selection on staging.
5. Enable `referrals` only for the planned canary payload/allowlist through audited admin controls.
6. Observe `kelbet_referral_funnel_total` and `process_referral_rewards` worker outcomes for at least
   one full waiting period before widening the canary.
7. Compare admin reward rows with payment orders, Stars observations and credit transactions.

Do not enable referrals merely because `PAYMENTS_ENABLED=true`. The payment live gate and
reconciliation health are independent prerequisites.

## Operator triage

The admin referral view is read-only for both `support` and `admin`. It exposes UUIDs, state,
snapshotted bonus amounts, safe timestamps and bounded review reasons; it does not expose referral
codes, Telegram IDs, payment charge IDs or raw gateway payloads.

- `pending`: no reconciled qualifying first purchase yet.
- `eligible`: qualifying purchase observed; waiting for `eligible_at` or daily-cap capacity.
- `credited`: both configured WalletService credits completed idempotently.
- `cancelled`: below minimum, reversed before credit or no longer backed by an active paid order.
- `needs_review`: suspicious attribution velocity, missing invariant data or reversal after credit.

For `needs_review`, compare only server-owned order/receipt/observation/ledger records. Record any
manual remediation as a separate audited admin action; never mutate attribution.

## Incident response and rollback

1. Set DB flag `referrals=false` through the audited admin control. This immediately blocks new
   links, attribution and worker crediting while preserving evidence.
2. Keep Stars reconciliation running read-only so later reversals are still classified.
3. Do not delete referral rows or credit transactions. Do not issue automatic negative debits.
4. Inspect worker failures and funnel spikes using bounded labels only; never add user/code/order
   identifiers to metrics.
5. Fix and deploy, then replay the idempotent reward worker. Already credited rewards cannot double
   credit; due eligible rewards resume safely.
6. Re-enable only for the canary after the discrepancy is understood.

Escalate immediately if there is evidence of duplicate ledger credit, attribution mutation, a
reward without a reconciled purchase, or sensitive data in logs/metrics.
