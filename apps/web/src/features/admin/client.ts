import { z } from "zod";
import { requestApi } from "../../shared/api/client";
import { paymentReconciliationPath } from "./reconciliation";
import {
  adminControlsSchema,
  adminGenerationSchema,
  adminMeSchema,
  adminModerationDecisionSchema,
  adminPaymentReconciliationSchema,
  adminReferralRewardSchema,
  adminPaymentsSchema,
  adminUserSchema,
  adminUserSummarySchema,
  auditEventSchema,
  auditMutationResponseSchema,
  ledgerItemSchema,
  type SafeActionInput,
  type ModerationReviewOutcome,
  type ReconciliationIssueStatus,
} from "./types";

const page = <T extends z.ZodType>(item: T) => z.object({ items: z.array(item) });

function queryString(values: Record<string, string | number>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) params.set(key, String(value));
  return params.toString();
}

function actionRequest(path: string, actionId: string, json: unknown, method = "POST") {
  return requestApi(path, auditMutationResponseSchema, {
    method,
    headers: { "Idempotency-Key": actionId },
    json,
  });
}

export const adminApi = {
  me: () => requestApi("/api/v1/admin/me", adminMeSchema),

  async searchUsers(query: string) {
    const data = await requestApi(
      `/api/v1/admin/users?${queryString({ q: query, limit: 25 })}`,
      page(adminUserSummarySchema),
    );
    return data.items;
  },

  getUser: (userId: string) =>
    requestApi(`/api/v1/admin/users/${encodeURIComponent(userId)}`, adminUserSchema),

  async ledger(userId: string) {
    const data = await requestApi(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/ledger?limit=50&offset=0`,
      page(ledgerItemSchema),
    );
    return data.items;
  },

  async generations(userId: string) {
    const data = await requestApi(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/generations?limit=50&offset=0`,
      page(adminGenerationSchema),
    );
    return data.items;
  },

  payments: (userId: string) =>
    requestApi(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/payments?limit=50&offset=0`,
      adminPaymentsSchema,
    ),

  controls: () => requestApi("/api/v1/admin/controls", adminControlsSchema),

  reconciliation: (status?: ReconciliationIssueStatus, offset = 0) =>
    requestApi(
      paymentReconciliationPath(status, offset),
      adminPaymentReconciliationSchema,
    ),

  async referrals() {
    const data = await requestApi(
      "/api/v1/admin/referrals?limit=100&offset=0",
      page(adminReferralRewardSchema),
    );
    return data.items;
  },

  async audit() {
    const data = await requestApi("/api/v1/admin/audit?limit=75&offset=0", page(auditEventSchema));
    return data.items;
  },

  async moderation(status: "open" | "reviewed") {
    const data = await requestApi(
      `/api/v1/admin/moderation?${queryString({ status, limit: 100, offset: 0 })}`,
      page(adminModerationDecisionSchema),
    );
    return data.items;
  },

  reviewModeration: (
    decisionId: string,
    outcome: ModerationReviewOutcome,
    input: SafeActionInput,
    actionId: string,
  ) =>
    actionRequest(
      `/api/v1/admin/moderation/${encodeURIComponent(decisionId)}/review`,
      actionId,
      { outcome, ...input },
    ),

  grantCredits: (userId: string, amount: number, input: SafeActionInput, actionId: string) =>
    actionRequest(`/api/v1/admin/users/${encodeURIComponent(userId)}/grant-credits`, actionId, {
      amount,
      ...input,
    }),

  setBlocked: (userId: string, blocked: boolean, input: SafeActionInput, actionId: string) =>
    actionRequest(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/${blocked ? "block" : "unblock"}`,
      actionId,
      input,
    ),

  refundGeneration: (generationId: string, input: SafeActionInput, actionId: string) =>
    actionRequest(
      `/api/v1/admin/generations/${encodeURIComponent(generationId)}/refund`,
      actionId,
      input,
    ),

  requestPaymentRefund: (
    orderId: string,
    input: SafeActionInput,
    actionId: string,
  ) =>
    actionRequest(
      `/api/v1/admin/payments/${encodeURIComponent(orderId)}/refund`,
      actionId,
      input,
    ),

  retryPaymentRefund: (
    refundId: string,
    input: SafeActionInput,
    actionId: string,
  ) =>
    actionRequest(
      `/api/v1/admin/payment-refunds/${encodeURIComponent(refundId)}/retry`,
      actionId,
      input,
    ),

  setModelEnabled: (slug: string, enabled: boolean, input: SafeActionInput, actionId: string) =>
    actionRequest(`/api/v1/admin/catalog/${encodeURIComponent(slug)}`, actionId, { enabled, ...input }, "PATCH"),

  setFeatureFlagEnabled: (key: string, enabled: boolean, input: SafeActionInput, actionId: string) =>
    actionRequest(`/api/v1/admin/feature-flags/${encodeURIComponent(key)}`, actionId, { enabled, ...input }, "PATCH"),

  setPaymentProductEnabled: (slug: string, enabled: boolean, input: SafeActionInput, actionId: string) =>
    actionRequest(`/api/v1/admin/payment-products/${encodeURIComponent(slug)}`, actionId, { enabled, ...input }, "PATCH"),

  setTemplateConfig: (
    slug: string,
    enabled: boolean,
    displayOrder: number,
    input: SafeActionInput,
    actionId: string,
  ) =>
    actionRequest(
      `/api/v1/admin/templates/${encodeURIComponent(slug)}`,
      actionId,
      { enabled, display_order: displayOrder, ...input },
      "PATCH",
    ),
};
