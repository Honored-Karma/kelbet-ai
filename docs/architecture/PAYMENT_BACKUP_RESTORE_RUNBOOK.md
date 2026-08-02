# Payment backup, restore, and reconciliation runbook

This repository does not prove that Railway managed point-in-time recovery (PITR) is enabled.
Before live purchases, the project owner must attach provider evidence for backup retention,
encryption, tested RPO/RTO, and the latest restore drill. PITR is an external live gate.

## Drill

1. Set `PAYMENTS_ENABLED=false` to stop new invoices. Keep successful-payment handling deployed.
2. Identify a consistent PostgreSQL backup and record its timestamp and provider backup ID.
3. Restore into an isolated database, never over production, and migrate through
   `0022_payment_hardening`.
4. Compare counts and invariants for orders, receipts, payment ledger rows, refunds, normalized
   Star observations, and unresolved reconciliation issues.
5. Run an isolated reconciliation with refunds disabled. A run marked
   `coverage_complete=false`/`telegram_history_truncated` may open issues but must not resolve
   existing issues.
6. Verify each paid/refunded/disputed order against its single processed receipt and ledger key.
   Record order-safe `KLB-…` support references; do not copy raw charge IDs into tickets.
7. Record achieved RPO/RTO, evidence links, unresolved cases, finance approval, and support approval.
   Re-enable only the canary Telegram IDs after sign-off.

Transaction-history recovery can reconstruct a proven missing receipt and credit idempotently.
It is not a durable Telegram update inbox; webhook/update durability remains a separate production
work item and must stay on the operational risk register.

## Downgrading past 0022

`0022_payment_hardening` replaced the unconditional unique constraint on
`payment_receipts.order_id` with a partial index limited to processed receipts, so a rejected
duplicate-charge receipt may legitimately share an order with the processed one. Its `downgrade()`
refuses to run while such duplicates exist rather than aborting halfway with a bare
`UniqueViolation`. Resolve or archive the extra receipts first, then downgrade.
