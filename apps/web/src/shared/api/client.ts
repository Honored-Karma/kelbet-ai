import {
  ApiError,
  assetDownloadSchema,
  authResponseSchema,
  catalogModelSchema,
  completedUploadSchema,
  generationDraftSchema,
  generationSchema,
  generationTemplateSchema,
  historyItemSchema,
  meSchema,
  creditTransactionSchema,
  moderationConfigSchema,
  paymentOrderSchema,
  paymentProductsSchema,
  promptAssistantConfigSchema,
  promptAssistantResultSchema,
  presignedUploadSchema,
  quoteSchema,
  referralSummarySchema,
  type AssetDownload,
  type AuthResponse,
  type CatalogModel,
  type CompletedUpload,
  type CreditTransaction,
  type Generation,
  type GenerationDraft,
  type GenerationDraftMode,
  type GenerationTemplate,
  type HistoryItem,
  type Language,
  type Me,
  type ModerationConfig,
  type PaymentOrder,
  type PaymentProducts,
  type PromptAssistantConfig,
  type PromptAssistantIntent,
  type PromptAssistantResult,
  type PresignedUpload,
  type Quote,
  type ReferralSummary,
} from "./types";
import { validateApiBaseUrl } from "./config";
import { z } from "zod";

/**
 * Включён ли mock-режим — решается на сборке, а не в рантайме.
 *
 * Логика намеренно повторяет getApiMode(), но записана через литералы
 * import.meta.env, чтобы Rollup свернул её в константу. При production-сборке
 * значение становится false, все ветки ниже удаляются вместе с единственной
 * ссылкой на loadMock, и мок-API (около 47 КБ) не попадает в бандл вовсе.
 * Раньше он ехал пользователю: ветвление происходило внутри функций, поэтому
 * tree-shaking снять его не мог.
 */
const MOCK_ENABLED: boolean =
  import.meta.env.VITE_API_MODE === "mock" ||
  (import.meta.env.VITE_API_MODE !== "live" && import.meta.env.DEV);

type MockApi = (typeof import("./mock"))["mockApi"];
let mockApiPromise: Promise<MockApi> | null = null;

/** Загружает мок один раз и переиспользует. Вызывается только под MOCK_ENABLED. */
function loadMock(): Promise<MockApi> {
  mockApiPromise ??= import("./mock").then((module) => module.mockApi);
  return mockApiPromise;
}

const TOKEN_KEY = "kelbet.access_token";

/**
 * Сессия признана недействительной сервером. Слушатель живёт внутри роутера и
 * отправляет пользователя на /boot, где initData обменивается на новый токен.
 * Событие, а не прямой вызов навигации, — чтобы транспортный слой не зависел от
 * react-router.
 */
export const UNAUTHORIZED_EVENT = "kelbet:unauthorized";

/** Единственный путь, которому позволено отвечать 401 без сброса сессии. */
const AUTH_PATH_PREFIX = "/api/v1/auth/";

export function getApiMode(): "mock" | "live" {
  const mode = import.meta.env.VITE_API_MODE;
  if (mode === "live" || mode === "mock") {
    return mode;
  }
  return import.meta.env.DEV ? "mock" : "live";
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (!token) {
    sessionStorage.removeItem(TOKEN_KEY);
    return;
  }
  sessionStorage.setItem(TOKEN_KEY, token);
}

function baseUrl(): string {
  const validation = validateApiBaseUrl(import.meta.env.VITE_API_BASE_URL, {
    production: import.meta.env.PROD,
  });
  if (!validation.ok) {
    throw new ApiError("api_configuration_error", validation.reason, 0);
  }
  return validation.url;
}

async function liveRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let body = init?.body;
  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      headers,
      body,
    });
  } catch {
    throw new ApiError("network_error", "KELBET API is unreachable", 0);
  }
  if (response.status === 401 && !path.startsWith(AUTH_PATH_PREFIX)) {
    // Протухший или отозванный токен раньше превращался в ошибку внутри
    // карточки: пользователь видел «что-то пошло не так» на каждом экране и
    // ничего не мог сделать, потому что переавторизации не существовало.
    setToken(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
  }
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = z
      .object({
        error: z.object({
          code: z.string(),
          message: z.string(),
        }),
      })
      .safeParse(payload);
    if (error.success) {
      throw new ApiError(error.data.error.code, error.data.error.message, response.status);
    }
    throw new ApiError("http_error", `HTTP ${response.status}`, response.status);
  }
  return schema.parse(payload);
}

export { liveRequest as requestApi };

export const api = {
  async authTelegram(initData: string): Promise<AuthResponse> {
    if (MOCK_ENABLED) {
      return (await loadMock()).authTelegram(initData);
    }
    return liveRequest("/api/v1/auth/telegram", authResponseSchema, {
      method: "POST",
      json: { init_data: initData },
    });
  },

  async getMe(): Promise<Me> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getMe();
    }
    return liveRequest("/api/v1/me", meSchema);
  },

  async getReferralSummary(): Promise<ReferralSummary> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getReferralSummary();
    }
    return liveRequest("/api/v1/referrals/me", referralSummarySchema);
  },

  async getModerationConfig(): Promise<ModerationConfig> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getModerationConfig();
    }
    return liveRequest("/api/v1/moderation/config", moderationConfigSchema);
  },

  async patchMe(payload: {
    language?: Language;
    notify_generation_ready?: boolean;
  }): Promise<Me> {
    if (MOCK_ENABLED) {
      return (await loadMock()).patchMe(payload);
    }
    return liveRequest("/api/v1/me", meSchema, { method: "PATCH", json: payload });
  },

  async listModels(lang?: Language): Promise<CatalogModel[]> {
    if (MOCK_ENABLED) {
      return (await loadMock()).listModels();
    }
    const query = lang ? `?lang=${lang}` : "";
    const data = await liveRequest(
      `/api/v1/catalog/models${query}`,
      z.object({ items: z.array(catalogModelSchema) }),
    );
    return data.items;
  },

  async listTemplates(lang?: Language, kind?: "image" | "video"): Promise<GenerationTemplate[]> {
    if (MOCK_ENABLED) {
      return (await loadMock()).listTemplates(lang, kind);
    }
    const params = new URLSearchParams();
    if (lang) params.set("lang", lang);
    if (kind) params.set("kind", kind);
    const query = params.size ? `?${params.toString()}` : "";
    const data = await liveRequest(
      `/api/v1/catalog/templates${query}`,
      z.object({ items: z.array(generationTemplateSchema) }),
    );
    return data.items;
  },

  async quote(
    modelSlug: string,
    params: Record<string, unknown>,
    template?: { templateId: string | null; templateInputs: Record<string, unknown> },
  ): Promise<Quote> {
    if (MOCK_ENABLED) {
      return (await loadMock()).quote(modelSlug, params, template);
    }
    return liveRequest("/api/v1/wallet/quote", quoteSchema, {
      method: "POST",
      json: {
        model_slug: modelSlug,
        params,
        template_id: template?.templateId ?? null,
        template_inputs: template?.templateInputs ?? {},
      },
    });
  },

  async listPaymentProducts(): Promise<PaymentProducts> {
    if (MOCK_ENABLED) {
      return (await loadMock()).listPaymentProducts();
    }
    return liveRequest("/api/v1/payments/products", paymentProductsSchema);
  },

  async createPaymentOrder(input: {
    productSlug: string;
    termsAccepted: boolean;
    termsVersion: string;
    idempotencyKey: string;
  }): Promise<PaymentOrder> {
    if (MOCK_ENABLED) {
      return (await loadMock()).createPaymentOrder(input);
    }
    // The server treats a present-but-mismatched terms version as a hard
    // validation error, so an unloaded catalogue must not be reported as the
    // empty version — omitting the field yields the accurate "version required"
    // response instead of a misleading mismatch.
    const payload: Record<string, unknown> = {
      product_slug: input.productSlug,
      terms_accepted: input.termsAccepted,
    };
    const termsVersion = input.termsVersion.trim();
    if (termsVersion) {
      payload.terms_version = termsVersion;
    }
    return liveRequest("/api/v1/payments/orders", paymentOrderSchema, {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      json: payload,
    });
  },

  async reopenPaymentOrder(orderId: string): Promise<PaymentOrder> {
    if (MOCK_ENABLED) {
      return (await loadMock()).reopenPaymentOrder(orderId);
    }
    return liveRequest(
      `/api/v1/payments/orders/${encodeURIComponent(orderId)}/invoice`,
      paymentOrderSchema,
      { method: "POST" },
    );
  },

  async walletTransactions(limit = 50): Promise<CreditTransaction[]> {
    if (MOCK_ENABLED) {
      return (await loadMock()).walletTransactions(limit);
    }
    const data = await liveRequest(
      `/api/v1/wallet/transactions?limit=${limit}`,
      z.object({ items: z.array(creditTransactionSchema) }),
    );
    return data.items;
  },

  async paymentHistory(): Promise<PaymentOrder[]> {
    if (MOCK_ENABLED) {
      return (await loadMock()).paymentHistory();
    }
    const data = await liveRequest(
      "/api/v1/payments/history",
      z.object({ items: z.array(paymentOrderSchema) }),
    );
    return data.items;
  },

  async presignUpload(file: File): Promise<PresignedUpload> {
    if (MOCK_ENABLED) {
      return (await loadMock()).presignUpload(file);
    }
    return liveRequest("/api/v1/uploads/presign", presignedUploadSchema, {
      method: "POST",
      json: {
        content_type: file.type,
        byte_size: file.size,
        role: "input",
      },
    });
  },

  async completeUpload(assetId: string): Promise<CompletedUpload> {
    if (MOCK_ENABLED) {
      return (await loadMock()).completeUpload(assetId);
    }
    return liveRequest(`/api/v1/uploads/${assetId}/complete`, completedUploadSchema, {
      method: "POST",
    });
  },

  async uploadPresigned(presigned: PresignedUpload, file: File): Promise<void> {
    if (MOCK_ENABLED) {
      return;
    }
    const headers = new Headers(presigned.headers);
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", file.type);
    }
    const response = await fetch(presigned.upload_url, {
      method: "PUT",
      headers,
      body: file,
    });
    if (!response.ok) {
      throw new ApiError("upload_failed", `HTTP ${response.status}`, response.status);
    }
  },

  async uploadAsset(file: File): Promise<CompletedUpload> {
    if (MOCK_ENABLED) {
      return (await loadMock()).uploadAsset(file);
    }
    const presigned = await this.presignUpload(file);
    await this.uploadPresigned(presigned, file);
    return this.completeUpload(presigned.asset_id);
  },

  async getAsset(assetId: string): Promise<AssetDownload> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getAsset(assetId);
    }
    return liveRequest(`/api/v1/assets/${assetId}`, assetDownloadSchema);
  },

  async getAssets(assetIds: string[]): Promise<AssetDownload[]> {
    if (!assetIds.length) return [];
    if (MOCK_ENABLED) {
      return (await loadMock()).getAssets(assetIds);
    }
    const data = await liveRequest(
      "/api/v1/assets/downloads",
      z.object({ items: z.array(assetDownloadSchema) }),
      { method: "POST", json: { asset_ids: assetIds } },
    );
    return data.items;
  },

  async getPromptAssistantConfig(): Promise<PromptAssistantConfig> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getPromptAssistantConfig();
    }
    return liveRequest("/api/v1/prompt-assistant/config", promptAssistantConfigSchema);
  },

  async improvePrompt(input: {
    brief: string;
    targetLanguage: Language;
    intent: PromptAssistantIntent;
    idempotencyKey: string;
  }): Promise<PromptAssistantResult> {
    if (MOCK_ENABLED) {
      return (await loadMock()).improvePrompt(input);
    }
    return liveRequest("/api/v1/prompt-assistant/improve", promptAssistantResultSchema, {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      json: {
        brief: input.brief,
        target_language: input.targetLanguage,
        intent: input.intent,
      },
    });
  },

  async createGeneration(input: {
    quoteId: string;
    prompt: string;
    idempotencyKey: string;
    inputAssetIds?: string[];
    rightsConsentConfirmed?: boolean;
    rightsConsentVersion?: string;
    templateId?: string | null;
    templateInputs?: Record<string, unknown>;
  }): Promise<Generation> {
    if (MOCK_ENABLED) {
      return (await loadMock()).createGeneration(input);
    }
    return liveRequest("/api/v1/generations", generationSchema, {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      json: {
        quote_id: input.quoteId,
        prompt: input.prompt,
        input_asset_ids: input.inputAssetIds ?? [],
        rights_consent_confirmed: input.rightsConsentConfirmed ?? false,
        rights_consent_version: input.rightsConsentVersion ?? null,
        template_id: input.templateId ?? null,
        template_inputs: input.templateInputs ?? {},
      },
    });
  },

  async getGeneration(id: string): Promise<Generation> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getGeneration(id);
    }
    return liveRequest(`/api/v1/generations/${encodeURIComponent(id)}`, generationSchema);
  },

  async getGenerationDraft(
    id: string,
    mode: GenerationDraftMode,
  ): Promise<GenerationDraft> {
    if (MOCK_ENABLED) {
      return (await loadMock()).getGenerationDraft(id, mode);
    }
    return liveRequest(
      `/api/v1/generations/${encodeURIComponent(id)}/draft?mode=${mode}`,
      generationDraftSchema,
    );
  },

  async cancelGeneration(id: string): Promise<Generation> {
    if (MOCK_ENABLED) {
      return (await loadMock()).cancelGeneration(id);
    }
    return liveRequest(`/api/v1/generations/${encodeURIComponent(id)}/cancel`, generationSchema, {
      method: "POST",
    });
  },

  async history(): Promise<HistoryItem[]> {
    if (MOCK_ENABLED) {
      return (await loadMock()).history();
    }
    const data = await liveRequest(
      "/api/v1/history",
      z.object({ items: z.array(historyItemSchema) }),
    );
    return data.items;
  },
};
