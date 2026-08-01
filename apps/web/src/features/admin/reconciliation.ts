import type {
  AdminReconciliationIssue,
  PaymentRefundStatus,
  ReconciliationIssueStatus,
} from "./types";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_DETAIL_KEYS = new Set([
  "direction",
  "amount",
  "telegram_amount",
  "receipt_amount",
  "classification",
  "telegram_exposes_explicit_chargeback_type",
  "ledger_transaction_id",
  "error_code",
]);

export function isPaymentRefundRetryable(status: PaymentRefundStatus): boolean {
  return status === "failed" || status === "needs_review";
}

export function paymentReconciliationPath(
  status?: ReconciliationIssueStatus,
  offset = 0,
): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", "100");
  params.set("offset", String(Math.max(0, offset)));
  return `/api/v1/admin/payment-reconciliation?${params.toString()}`;
}

export function isValidAdminUuid(value: string): boolean {
  return UUID_PATTERN.test(value.trim());
}

export function safeIssueDetails(
  issue: AdminReconciliationIssue,
): Array<[string, string]> {
  return Object.entries(issue.details)
    .filter(([key]) => SAFE_DETAIL_KEYS.has(key))
    .map(([key, value]) => [key, value === null ? "—" : String(value)]);
}
