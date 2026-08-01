import type { AdminPaymentReconciliation } from "./types";

export const ADMIN_RECONCILIATION_MOCK: AdminPaymentReconciliation = {
  refunds: [
    {
      id: "7f903728-941b-4c30-86fc-f3e3cf87c339",
      order_id: "0cc33760-bfad-4370-9568-fac4bed47fca",
      status: "needs_review",
      stars_amount: 270,
      credits_amount: 300,
      attempt_count: 2,
      last_error_code: "telegram_refund_pending",
      external_refunded_at: null,
      ledger_transaction_id: null,
      requested_at: "2026-08-01T09:20:00Z",
      finished_at: null,
    },
  ],
  issues: [
    {
      id: "47a0046d-0a0d-43c3-95bf-72e2040e54a9",
      kind: "transaction_amount_mismatch",
      status: "needs_review",
      severity: "critical",
      order_id: "0cc33760-bfad-4370-9568-fac4bed47fca",
      refund_id: "7f903728-941b-4c30-86fc-f3e3cf87c339",
      details: { telegram_amount: 270, receipt_amount: 300 },
      first_seen_at: "2026-08-01T09:22:00Z",
      last_seen_at: "2026-08-01T09:30:00Z",
      resolved_at: null,
    },
  ],
  latest_run: {
    id: "ef7e71eb-e9f6-4663-8c17-6e0df176a367",
    status: "completed",
    fetched_count: 124,
    issue_count: 1,
    started_at: "2026-08-01T09:29:00Z",
    finished_at: "2026-08-01T09:30:00Z",
    error_code: null,
  },
};
