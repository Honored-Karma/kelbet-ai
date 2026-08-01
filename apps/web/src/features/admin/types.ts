import { z } from "zod";

export const adminCapabilitiesSchema = z.union([
  z.array(z.string()),
  z.record(z.string(), z.boolean()),
]);

export const adminMeSchema = z.object({
  user_id: z.string().uuid(),
  telegram_id: z.number().int(),
  username: z.string().nullable(),
  role: z.enum(["support", "admin"]),
  bootstrap: z.boolean(),
  capabilities: adminCapabilitiesSchema,
});
export type AdminMe = z.infer<typeof adminMeSchema>;

export const adminUserSummarySchema = z.object({
  id: z.string().uuid(),
  telegram_id: z.number().int(),
  username: z.string().nullable(),
  is_blocked: z.boolean(),
});
export type AdminUserSummary = z.infer<typeof adminUserSummarySchema>;

export const adminUserSchema = adminUserSummarySchema.extend({
  language: z.string(),
  plan: z.string(),
  blocked_at: z.string().nullable(),
  blocked_reason: z.string().nullable(),
  created_at: z.string(),
  wallet: z
    .object({
      id: z.string().uuid(),
      balance: z.number().int(),
      reserved: z.number().int(),
      available: z.number().int(),
      version: z.number().int(),
    })
    .nullable(),
});
export type AdminUser = z.infer<typeof adminUserSchema>;

export const ledgerItemSchema = z.object({
  id: z.string().uuid(),
  type: z.string(),
  reason: z.string(),
  amount: z.number().int(),
  balance_after: z.number().int(),
  created_at: z.string(),
});
export type LedgerItem = z.infer<typeof ledgerItemSchema>;

export const adminGenerationSchema = z.object({
  id: z.string().uuid(),
  status: z.string(),
  modality: z.string(),
  provider: z.string(),
  provider_model_id: z.string(),
  error_code: z.string().nullable(),
  error_class: z.string().nullable(),
  attempt_count: z.number().int(),
  user_credit_price: z.number().int(),
  reservation_id: z.string().uuid().nullable(),
  correlation_id: z.string().uuid(),
  created_at: z.string(),
  finished_at: z.string().nullable(),
});
export type AdminGeneration = z.infer<typeof adminGenerationSchema>;

export const adminPaymentOrderSchema = z.object({
  id: z.string().uuid(),
  status: z.string(),
  product_slug: z.string(),
  credits: z.number().int(),
  currency: z.string(),
  total_amount: z.number().int(),
  created_at: z.string(),
  paid_at: z.string().nullable(),
});
export type AdminPaymentOrder = z.infer<typeof adminPaymentOrderSchema>;

export const adminPaymentReceiptSchema = z.object({
  id: z.string().uuid(),
  order_id: z.string().uuid().nullable(),
  status: z.string(),
  currency: z.string(),
  total_amount: z.number().int(),
  error_code: z.string().nullable(),
  created_at: z.string(),
  processed_at: z.string().nullable(),
});

export const adminPaymentsSchema = z.object({
  orders: z.array(adminPaymentOrderSchema),
  receipts: z.array(adminPaymentReceiptSchema),
});
export type AdminPayments = z.infer<typeof adminPaymentsSchema>;

export const paymentRefundStatusSchema = z.enum([
  "requested",
  "processing",
  "refunded",
  "failed",
  "needs_review",
]);
export type PaymentRefundStatus = z.infer<typeof paymentRefundStatusSchema>;

export const adminPaymentRefundSchema = z
  .object({
    id: z.string().uuid(),
    order_id: z.string().uuid(),
    status: paymentRefundStatusSchema,
    stars_amount: z.number().int().nonnegative(),
    credits_amount: z.number().int().nonnegative(),
    attempt_count: z.number().int().nonnegative(),
    last_error_code: z.string().nullable(),
    external_refunded_at: z.string().nullable(),
    ledger_transaction_id: z.string().uuid().nullable(),
    requested_at: z.string(),
    finished_at: z.string().nullable(),
  })
  .strict();
export type AdminPaymentRefund = z.infer<typeof adminPaymentRefundSchema>;

const reconciliationDetailValueSchema = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.null(),
]);

export const reconciliationIssueStatusSchema = z.enum([
  "open",
  "resolved",
  "needs_review",
]);
export type ReconciliationIssueStatus = z.infer<typeof reconciliationIssueStatusSchema>;

export const adminReconciliationIssueSchema = z
  .object({
    id: z.string().uuid(),
    kind: z.string(),
    status: reconciliationIssueStatusSchema,
    severity: z.string(),
    order_id: z.string().uuid().nullable(),
    refund_id: z.string().uuid().nullable(),
    details: z
      .object({
        direction: reconciliationDetailValueSchema.optional(),
        amount: reconciliationDetailValueSchema.optional(),
        telegram_amount: reconciliationDetailValueSchema.optional(),
        receipt_amount: reconciliationDetailValueSchema.optional(),
        classification: reconciliationDetailValueSchema.optional(),
        telegram_exposes_explicit_chargeback_type: reconciliationDetailValueSchema.optional(),
        ledger_transaction_id: reconciliationDetailValueSchema.optional(),
        error_code: reconciliationDetailValueSchema.optional(),
      })
      .strict(),
    first_seen_at: z.string(),
    last_seen_at: z.string(),
    resolved_at: z.string().nullable(),
  })
  .strict();
export type AdminReconciliationIssue = z.infer<typeof adminReconciliationIssueSchema>;

export const adminReconciliationRunSchema = z
  .object({
    id: z.string().uuid(),
    status: z.string(),
    fetched_count: z.number().int().nonnegative(),
    issue_count: z.number().int().nonnegative(),
    started_at: z.string(),
    finished_at: z.string().nullable(),
    error_code: z.string().nullable(),
  })
  .strict();

export const adminPaymentReconciliationSchema = z
  .object({
    refunds: z.array(adminPaymentRefundSchema),
    issues: z.array(adminReconciliationIssueSchema),
    latest_run: adminReconciliationRunSchema.nullable(),
  })
  .strict();
export type AdminPaymentReconciliation = z.infer<typeof adminPaymentReconciliationSchema>;

export const adminReferralRewardSchema = z
  .object({
    id: z.string().uuid(),
    status: z.enum(["pending", "eligible", "credited", "cancelled", "needs_review"]),
    inviter_user_id: z.string().uuid(),
    invited_user_id: z.string().uuid(),
    payment_order_id: z.string().uuid().nullable(),
    inviter_bonus_credits: z.number().int().nonnegative(),
    invitee_bonus_credits: z.number().int().nonnegative(),
    eligible_at: z.string().nullable(),
    credited_at: z.string().nullable(),
    review_reason: z.string().nullable(),
    created_at: z.string(),
  })
  .strict();
export type AdminReferralReward = z.infer<typeof adminReferralRewardSchema>;

export const adminControlsSchema = z.object({
  models: z.array(
    z.object({
      slug: z.string(),
      modality: z.string(),
      provider: z.string(),
      enabled: z.boolean(),
      feature_flag: z.string().nullable(),
      user_credit_price: z.number().int(),
    }),
  ),
  feature_flags: z.array(
    z.object({
      key: z.string(),
      enabled: z.boolean(),
    }),
  ),
  provider_health: z.array(
    z.object({
      provider: z.string(),
      modality: z.enum(["media", "image", "video"]),
      configured: z.boolean(),
      enabled: z.boolean(),
      canary: z.boolean(),
      status: z.enum(["disabled", "unconfigured", "degraded", "healthy", "ready"]),
      recent_successes: z.number().int().nonnegative(),
      recent_failures: z.number().int().nonnegative(),
      last_attempt_at: z.string().nullable(),
    }),
  ),
  payment_products: z.array(
    z.object({
      slug: z.string(),
      credits: z.number().int(),
      stars: z.number().int(),
      enabled: z.boolean(),
    }),
  ),
  templates: z.array(
    z.object({
      slug: z.string(),
      version: z.number().int().positive(),
      kind: z.enum(["image", "video"]),
      enabled: z.boolean(),
      display_order: z.number().int().nonnegative(),
      localization: z.record(z.string(), z.unknown()),
    }),
  ),
});
export type AdminControls = z.infer<typeof adminControlsSchema>;

export const moderationReviewOutcomeSchema = z.enum([
  "confirmed_violation",
  "false_positive",
  "needs_escalation",
]);
export type ModerationReviewOutcome = z.infer<typeof moderationReviewOutcomeSchema>;

export const adminModerationDecisionSchema = z
  .object({
    id: z.string().uuid(),
    user_id: z.string().uuid(),
    generation_id: z.string().uuid().nullable(),
    asset_ids: z.array(z.string().uuid()),
    context: z.string(),
    input_hash: z.string(),
    mode: z.enum(["off", "report", "block"]),
    outcome: z.enum(["allow", "report", "block"]),
    reason_codes: z.array(z.string()),
    policy_version: z.string(),
    provider: z.string(),
    provider_model: z.string().nullable(),
    error_code: z.string().nullable(),
    review_status: z.enum(["open", "reviewed"]),
    review_outcome: moderationReviewOutcomeSchema.nullable(),
    reviewed_at: z.string().nullable(),
    created_at: z.string(),
  })
  .strict();
export type AdminModerationDecision = z.infer<typeof adminModerationDecisionSchema>;

const safeSnapshotSchema = z.record(
  z.string(),
  z.union([z.string(), z.number(), z.boolean(), z.null()]),
);

export const auditEventSchema = z.object({
  id: z.string().uuid(),
  action_id: z.string().uuid(),
  operator_user_id: z.string().uuid(),
  operator_role: z.string(),
  action: z.string(),
  object_type: z.string(),
  object_id: z.string(),
  before: safeSnapshotSchema,
  after: safeSnapshotSchema,
  reason: z.string(),
  reference: z.string(),
  correlation_id: z.string().uuid(),
  created_at: z.string(),
});
export type AuditEvent = z.infer<typeof auditEventSchema>;

export const auditMutationResponseSchema = z
  .union([auditEventSchema, z.object({ audit: auditEventSchema })])
  .transform((value) => ("audit" in value ? value.audit : value));

export type SafeActionInput = {
  reason: string;
  reference: string;
};
