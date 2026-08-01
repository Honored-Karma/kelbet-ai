import assert from "node:assert/strict";
import test from "node:test";

import { canRenderAdminAction } from "../src/features/admin/permissions.ts";
import {
  isPaymentRefundRetryable,
  isValidAdminUuid,
  paymentReconciliationPath,
  safeIssueDetails,
} from "../src/features/admin/reconciliation.ts";
import { ADMIN_RECONCILIATION_MOCK } from "../src/features/admin/reconciliationMock.ts";
import {
  adminPaymentReconciliationSchema,
  type AdminMe,
} from "../src/features/admin/types.ts";

function operator(role: "support" | "admin", capabilities: string[]): AdminMe {
  return {
    user_id: "4763b49b-478a-45e6-befd-5c9f25e92579",
    telegram_id: 123456,
    username: role,
    role,
    bootstrap: false,
    capabilities,
  };
}

test("reconciliation mock fixture satisfies the strict API contract", () => {
  const parsed = adminPaymentReconciliationSchema.parse(ADMIN_RECONCILIATION_MOCK);
  assert.equal(parsed.refunds[0]?.status, "needs_review");
  assert.equal(parsed.issues[0]?.severity, "critical");
  assert.equal(parsed.latest_run?.status, "completed");
});

test("issue details reject nested or raw payloads", () => {
  const unsafe = structuredClone(ADMIN_RECONCILIATION_MOCK);
  unsafe.issues[0]!.details = {
    raw_payload: { payment_charge_id: "must-not-render" },
  } as never;
  assert.equal(adminPaymentReconciliationSchema.safeParse(unsafe).success, false);
  unsafe.issues[0]!.details = { raw_payload: "must-not-cache" } as never;
  assert.equal(adminPaymentReconciliationSchema.safeParse(unsafe).success, false);
});

test("support reads reconciliation while payment refund actions stay admin-only", () => {
  assert.equal(canRenderAdminAction(operator("support", ["read"]), "payment.refund"), false);
  assert.equal(
    canRenderAdminAction(operator("admin", ["read", "write"]), "payment.refund"),
    true,
  );
});

test("only failed and needs-review refunds can be retried", () => {
  assert.equal(isPaymentRefundRetryable("failed"), true);
  assert.equal(isPaymentRefundRetryable("needs_review"), true);
  assert.equal(isPaymentRefundRetryable("requested"), false);
  assert.equal(isPaymentRefundRetryable("processing"), false);
  assert.equal(isPaymentRefundRetryable("refunded"), false);
});

test("client status filter is encoded and safe details remain primitive", () => {
  assert.equal(
    paymentReconciliationPath("needs_review"),
    "/api/v1/admin/payment-reconciliation?status=needs_review&limit=100&offset=0",
  );
  assert.equal(
    paymentReconciliationPath(),
    "/api/v1/admin/payment-reconciliation?limit=100&offset=0",
  );
  assert.equal(
    paymentReconciliationPath("open", 200),
    "/api/v1/admin/payment-reconciliation?status=open&limit=100&offset=200",
  );
  const issue = adminPaymentReconciliationSchema.parse(ADMIN_RECONCILIATION_MOCK).issues[0]!;
  assert.deepEqual(safeIssueDetails(issue), [
    ["telegram_amount", "270"],
    ["receipt_amount", "300"],
  ]);
});

test("manual paid-order action accepts only an RFC UUID", () => {
  assert.equal(isValidAdminUuid("0cc33760-bfad-4370-9568-fac4bed47fca"), true);
  assert.equal(isValidAdminUuid("paid-order-123"), false);
  assert.equal(isValidAdminUuid("../../payments/order"), false);
});
