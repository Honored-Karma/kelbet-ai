import {
  ApiError,
  assetDownloadSchema,
  authResponseSchema,
  catalogModelSchema,
  completedUploadSchema,
  generationDraftSchema,
  generationSchema,
  historyItemSchema,
  meSchema,
  paymentOrderSchema,
  paymentProductsSchema,
  promptAssistantConfigSchema,
  promptAssistantResultSchema,
  presignedUploadSchema,
  quoteSchema,
  type AssetDownload,
  type AuthResponse,
  type CatalogModel,
  type CompletedUpload,
  type Generation,
  type GenerationDraft,
  type GenerationDraftMode,
  type HistoryItem,
  type Language,
  type Me,
  type PaymentOrder,
  type PaymentProducts,
  type PromptAssistantConfig,
  type PromptAssistantIntent,
  type PromptAssistantResult,
  type PresignedUpload,
  type Quote,
} from "./types";
import { mockApi } from "./mock";
import { z } from "zod";

const TOKEN_KEY = "kelbet.access_token";

export function getApiMode(): "mock" | "live" {
  const mode = import.meta.env.VITE_API_MODE;
  if (mode === "live" || mode === "mock") {
    return mode;
  }
  return "mock";
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
  return (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
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
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers,
    body,
  });
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

export const api = {
  async authTelegram(initData: string): Promise<AuthResponse> {
    if (getApiMode() === "mock") {
      return mockApi.authTelegram(initData);
    }
    return liveRequest("/api/v1/auth/telegram", authResponseSchema, {
      method: "POST",
      json: { init_data: initData },
    });
  },

  async getMe(): Promise<Me> {
    if (getApiMode() === "mock") {
      return mockApi.getMe();
    }
    return liveRequest("/api/v1/me", meSchema);
  },

  async patchMe(payload: {
    language?: Language;
    notify_generation_ready?: boolean;
  }): Promise<Me> {
    if (getApiMode() === "mock") {
      return mockApi.patchMe(payload);
    }
    return liveRequest("/api/v1/me", meSchema, { method: "PATCH", json: payload });
  },

  async listModels(lang?: Language): Promise<CatalogModel[]> {
    if (getApiMode() === "mock") {
      return mockApi.listModels();
    }
    const query = lang ? `?lang=${lang}` : "";
    const data = await liveRequest(
      `/api/v1/catalog/models${query}`,
      z.object({ items: z.array(catalogModelSchema) }),
    );
    return data.items;
  },

  async quote(modelSlug: string, params: Record<string, unknown>): Promise<Quote> {
    if (getApiMode() === "mock") {
      return mockApi.quote(modelSlug, params);
    }
    return liveRequest("/api/v1/wallet/quote", quoteSchema, {
      method: "POST",
      json: { model_slug: modelSlug, params },
    });
  },

  async listPaymentProducts(): Promise<PaymentProducts> {
    if (getApiMode() === "mock") {
      return mockApi.listPaymentProducts();
    }
    return liveRequest("/api/v1/payments/products", paymentProductsSchema);
  },

  async createPaymentOrder(input: {
    productSlug: string;
    termsAccepted: boolean;
    idempotencyKey: string;
  }): Promise<PaymentOrder> {
    if (getApiMode() === "mock") {
      return mockApi.createPaymentOrder(input);
    }
    return liveRequest("/api/v1/payments/orders", paymentOrderSchema, {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      json: {
        product_slug: input.productSlug,
        terms_accepted: input.termsAccepted,
      },
    });
  },

  async paymentHistory(): Promise<PaymentOrder[]> {
    if (getApiMode() === "mock") {
      return mockApi.paymentHistory();
    }
    const data = await liveRequest(
      "/api/v1/payments/history",
      z.object({ items: z.array(paymentOrderSchema) }),
    );
    return data.items;
  },

  async presignUpload(file: File): Promise<PresignedUpload> {
    if (getApiMode() === "mock") {
      return mockApi.presignUpload(file);
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
    if (getApiMode() === "mock") {
      return mockApi.completeUpload(assetId);
    }
    return liveRequest(`/api/v1/uploads/${assetId}/complete`, completedUploadSchema, {
      method: "POST",
    });
  },

  async uploadPresigned(presigned: PresignedUpload, file: File): Promise<void> {
    if (getApiMode() === "mock") {
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
    if (getApiMode() === "mock") {
      return mockApi.uploadAsset(file);
    }
    const presigned = await this.presignUpload(file);
    await this.uploadPresigned(presigned, file);
    return this.completeUpload(presigned.asset_id);
  },

  async getAsset(assetId: string): Promise<AssetDownload> {
    if (getApiMode() === "mock") {
      return mockApi.getAsset(assetId);
    }
    return liveRequest(`/api/v1/assets/${assetId}`, assetDownloadSchema);
  },

  async getAssets(assetIds: string[]): Promise<AssetDownload[]> {
    if (!assetIds.length) return [];
    if (getApiMode() === "mock") {
      return mockApi.getAssets(assetIds);
    }
    const data = await liveRequest(
      "/api/v1/assets/downloads",
      z.object({ items: z.array(assetDownloadSchema) }),
      { method: "POST", json: { asset_ids: assetIds } },
    );
    return data.items;
  },

  async getPromptAssistantConfig(): Promise<PromptAssistantConfig> {
    if (getApiMode() === "mock") {
      return mockApi.getPromptAssistantConfig();
    }
    return liveRequest("/api/v1/prompt-assistant/config", promptAssistantConfigSchema);
  },

  async improvePrompt(input: {
    brief: string;
    targetLanguage: Language;
    intent: PromptAssistantIntent;
    idempotencyKey: string;
  }): Promise<PromptAssistantResult> {
    if (getApiMode() === "mock") {
      return mockApi.improvePrompt(input);
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
  }): Promise<Generation> {
    if (getApiMode() === "mock") {
      return mockApi.createGeneration(input);
    }
    return liveRequest("/api/v1/generations", generationSchema, {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      json: {
        quote_id: input.quoteId,
        prompt: input.prompt,
        input_asset_ids: input.inputAssetIds ?? [],
      },
    });
  },

  async getGeneration(id: string): Promise<Generation> {
    if (getApiMode() === "mock") {
      return mockApi.getGeneration(id);
    }
    return liveRequest(`/api/v1/generations/${encodeURIComponent(id)}`, generationSchema);
  },

  async getGenerationDraft(
    id: string,
    mode: GenerationDraftMode,
  ): Promise<GenerationDraft> {
    if (getApiMode() === "mock") {
      return mockApi.getGenerationDraft(id, mode);
    }
    return liveRequest(
      `/api/v1/generations/${encodeURIComponent(id)}/draft?mode=${mode}`,
      generationDraftSchema,
    );
  },

  async cancelGeneration(id: string): Promise<Generation> {
    if (getApiMode() === "mock") {
      return mockApi.cancelGeneration(id);
    }
    return liveRequest(`/api/v1/generations/${encodeURIComponent(id)}/cancel`, generationSchema, {
      method: "POST",
    });
  },

  async history(): Promise<HistoryItem[]> {
    if (getApiMode() === "mock") {
      return mockApi.history();
    }
    const data = await liveRequest(
      "/api/v1/history",
      z.object({ items: z.array(historyItemSchema) }),
    );
    return data.items;
  },
};
