import { z } from "zod";

export const languageSchema = z.enum(["ru", "kk"]);
export type Language = z.infer<typeof languageSchema>;

export const meSchema = z.object({
  id: z.string(),
  telegram_id: z.number(),
  username: z.string().nullable(),
  language: languageSchema,
  plan: z.string(),
  balance: z.number().int(),
  reserved: z.number().int(),
  available: z.number().int(),
  notify_generation_ready: z.boolean(),
});
export type Me = z.infer<typeof meSchema>;

export const moderationConfigSchema = z
  .object({
    mode: z.enum(["off", "report", "block"]),
    policy_version: z.string(),
    photo_rights_consent_version: z.string(),
    support_route: z.string().startsWith("/"),
    image_moderation_supported: z.boolean(),
  })
  .strict();
export type ModerationConfig = z.infer<typeof moderationConfigSchema>;

export const promptAssistantIntentSchema = z.enum([
  "general",
  "product",
  "social",
  "portrait",
  "interior",
  "food",
  "fashion",
]);
export type PromptAssistantIntent = z.infer<typeof promptAssistantIntentSchema>;

export const promptAssistantConfigSchema = z.object({
  credit_cost: z.number().int().nonnegative(),
  max_input_chars: z.number().int().positive(),
  max_output_chars: z.number().int().positive(),
  charge_policy: z.literal("on_success"),
});
export type PromptAssistantConfig = z.infer<typeof promptAssistantConfigSchema>;

export const promptAssistantResultSchema = z.object({
  improved_prompt: z.string(),
  language: languageSchema,
  credit_cost: z.number().int().nonnegative(),
  charged: z.boolean(),
  balance: z.number().int(),
  limits: z.object({
    max_input_chars: z.number().int().positive(),
    max_output_chars: z.number().int().positive(),
  }),
});
export type PromptAssistantResult = z.infer<typeof promptAssistantResultSchema>;

export const catalogModelSchema = z.object({
  id: z.string(),
  slug: z.string(),
  modality: z.string(),
  provider: z.string(),
  provider_model_id: z.string(),
  display_order: z.number(),
  enabled: z.boolean(),
  deprecated: z.boolean(),
  replacement_slug: z.string().nullable(),
  user_credit_price: z.number().int(),
  capabilities: z.record(z.string(), z.unknown()),
  input_requirements: z.record(z.string(), z.unknown()),
  localization: z.object({
    name: z.string(),
    description: z.string(),
  }),
  pricing_rules: z.record(z.string(), z.unknown()).nullable(),
});
export type CatalogModel = z.infer<typeof catalogModelSchema>;

export const generationTemplateFieldSchema = z
  .object({
    key: z.string(),
    type: z.literal("text"),
    required: z.boolean(),
    max_length: z.number().int().positive(),
    label: z.union([
      z.string(),
      z.object({ ru: z.string(), kk: z.string() }).strict(),
    ]),
  })
  .strict();

export const generationTemplateSchema = z
  .object({
    id: z.string().min(1),
    slug: z.string(),
    version: z.number().int().positive(),
    kind: z.enum(["image", "video"]),
    display_order: z.number().int().nonnegative(),
    localization: z.object({
      name: z.string(),
      description: z.string(),
    }),
    prompt_preset: z.string(),
    aspect_ratio: z.string(),
    duration_sec: z.number().int().positive().nullable(),
    compatible_modalities: z.array(z.string()),
    required_inputs: z
      .object({
        assets: z.object({
          min: z.number().int().nonnegative(),
          max: z.number().int().nonnegative(),
        }),
        fields: z.array(generationTemplateFieldSchema),
      })
      .strict(),
    preview_metadata: z.record(z.string(), z.unknown()),
    compositor: z.string().nullable(),
  })
  .strict();
export type GenerationTemplate = z.infer<typeof generationTemplateSchema>;

export const quoteSchema = z.object({
  quote_id: z.string(),
  model_slug: z.string(),
  user_credit_price: z.number().int(),
  currency: z.string(),
  expires_at: z.string(),
  params: z.record(z.string(), z.unknown()),
  template_id: z.string().min(1).nullable(),
  template_slug: z.string().nullable(),
  template_version: z.number().int().positive().nullable(),
  template_inputs: z.record(z.string(), z.unknown()),
  available: z.number().int().optional(),
});
export type Quote = z.infer<typeof quoteSchema>;

export const presignedUploadSchema = z.object({
  asset_id: z.string(),
  upload_url: z.string(),
  object_key: z.string(),
  headers: z.record(z.string(), z.string()),
  expires_in: z.number().int(),
  max_bytes: z.number().int(),
});
export type PresignedUpload = z.infer<typeof presignedUploadSchema>;

export const completedUploadSchema = z.object({
  asset_id: z.string(),
  status: z.string(),
  content_type: z.string(),
  byte_size: z.number().int(),
  magic_ok: z.boolean(),
  width: z.number().int().positive().nullable(),
  height: z.number().int().positive().nullable(),
});
export type CompletedUpload = z.infer<typeof completedUploadSchema>;

export const assetDownloadSchema = z.object({
  id: z.string(),
  role: z.string(),
  content_type: z.string(),
  byte_size: z.number().int(),
  width: z.number().int().positive().nullable(),
  height: z.number().int().positive().nullable(),
  download_url: z.string(),
  expires_in: z.number().int(),
});
export type AssetDownload = z.infer<typeof assetDownloadSchema>;

export const generationSchema = z.object({
  id: z.string(),
  status: z.string(),
  modality: z.string(),
  model_slug: z.string().nullable(),
  template_slug: z.string().nullable(),
  template_version: z.number().int().positive().nullable(),
  user_credit_price: z.number().int(),
  progress_pct: z.number().int(),
  progress_stage: z.string().nullable(),
  error_code: z.string().nullable(),
  cancelable: z.boolean(),
  reservation_id: z.string().nullable().optional(),
  output_asset_ids: z.array(z.string()),
  created_at: z.string(),
  eta_seconds: z.number().int().positive().nullable().optional(),
  estimated_remaining_seconds: z.number().int().nonnegative().nullable().optional(),
});
export type Generation = z.infer<typeof generationSchema>;

export const generationDraftModeSchema = z.enum(["repeat", "remix", "upscale"]);
export type GenerationDraftMode = z.infer<typeof generationDraftModeSchema>;

export const generationDraftSchema = z.object({
  source_generation_id: z.string(),
  mode: generationDraftModeSchema,
  model_slug: z.string().nullable(),
  modality: z.string(),
  prompt: z.string(),
  params: z.record(z.string(), z.unknown()),
  input_asset_ids: z.array(z.string()),
  unavailable_asset_ids: z.array(z.string()),
  missing_input_assets: z.number().int().nonnegative(),
  model_available: z.boolean(),
  replacement_slug: z.string().nullable(),
  template_id: z.string().min(1).nullable(),
  template_slug: z.string().nullable(),
  template_version: z.number().int().positive().nullable(),
  template_inputs: z.record(z.string(), z.unknown()),
});
export type GenerationDraft = z.infer<typeof generationDraftSchema>;

export const historyItemSchema = z.object({
  id: z.string(),
  status: z.string(),
  modality: z.string(),
  model_slug: z.string().nullable(),
  user_credit_price: z.number().int(),
  progress_pct: z.number().int(),
  output_asset_ids: z.array(z.string()),
  preview_asset_id: z.string().nullable(),
  preview_content_type: z.string().nullable(),
  created_at: z.string(),
});
export type HistoryItem = z.infer<typeof historyItemSchema>;

export const authResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
  user: z.object({
    id: z.string(),
    language: languageSchema,
    plan: z.string(),
  }),
});
export type AuthResponse = z.infer<typeof authResponseSchema>;

export const paymentProductSchema = z.object({
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  credits: z.number().int().positive(),
  stars: z.number().int().positive(),
});
export type PaymentProduct = z.infer<typeof paymentProductSchema>;

export const paymentProductsSchema = z.object({
  items: z.array(paymentProductSchema),
  payments_enabled: z.boolean(),
  terms_url: z.string(),
});
export type PaymentProducts = z.infer<typeof paymentProductsSchema>;

export const paymentOrderSchema = z.object({
  id: z.string(),
  status: z.string(),
  product_slug: z.string(),
  product_name: z.string(),
  credits: z.number().int().positive(),
  currency: z.literal("XTR"),
  total_amount: z.number().int().positive(),
  invoice_url: z.string().nullable(),
  expires_at: z.string(),
  created_at: z.string(),
  paid_at: z.string().nullable(),
});
export type PaymentOrder = z.infer<typeof paymentOrderSchema>;

export const referralSummarySchema = z
  .object({
    enabled: z.boolean(),
    code: z.string().nullable(),
    link: z.string().url().nullable(),
    invited_count: z.number().int().nonnegative(),
    pending_rewards_count: z.number().int().nonnegative(),
    credited_rewards_count: z.number().int().nonnegative(),
    credited_bonus_credits: z.number().int().nonnegative(),
    inviter_bonus_credits: z.number().int().nonnegative(),
    invitee_bonus_credits: z.number().int().nonnegative(),
    minimum_purchase_stars: z.number().int().positive(),
    waiting_period_hours: z.number().int().nonnegative(),
  })
  .strict();
export type ReferralSummary = z.infer<typeof referralSummarySchema>;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}
