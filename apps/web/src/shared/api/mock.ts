import type {
  AssetDownload,
  AuthResponse,
  CatalogModel,
  CompletedUpload,
  Generation,
  GenerationDraft,
  GenerationDraftMode,
  GenerationPassport,
  GenerationTemplate,
  HistoryItem,
  Language,
  Me,
  ModerationConfig,
  PaymentOrder,
  PaymentProducts,
  PresignedUpload,
  PromptAssistantConfig,
  PromptAssistantIntent,
  PromptAssistantResult,
  Quote,
  ReferralSummary,
} from "./types";
import { ApiError } from "./types";
import mockResultUrl from "../../assets/mock-result.webp";

const nowIso = () => new Date().toISOString();
const MOCK_PROFILE_LANGUAGE_KEY = "kelbet.mock.profile-language";

function restoredProfileLanguage(): Language {
  if (typeof localStorage === "undefined") return "ru";
  try {
    const stored = localStorage.getItem(MOCK_PROFILE_LANGUAGE_KEY);
    return stored === "ru" || stored === "kk" ? stored : "ru";
  } catch {
    return "ru";
  }
}

async function imageDimensions(file: File): Promise<{ width: number | null; height: number | null }> {
  if (!("createImageBitmap" in globalThis)) return { width: null, height: null };
  try {
    const bitmap = await createImageBitmap(file);
    const dimensions = { width: bitmap.width || null, height: bitmap.height || null };
    bitmap.close();
    return dimensions;
  } catch {
    return { width: null, height: null };
  }
}

let language: Language = restoredProfileLanguage();
let balance = 420;
let reserved = 0;
let notifyGenerationReady = true;
const paymentOrders: PaymentOrder[] = [];
const paymentOrderRequests = new Map<string, PaymentOrder>();

const models: CatalogModel[] = [
  {
    id: "m1",
    slug: "mock-text",
    modality: "text",
    provider: "mock",
    provider_model_id: "mock-text-v1",
    display_order: 10,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 1,
    capabilities: { max_prompt_chars: 2000 },
    input_requirements: { prompt: "required" },
    localization: {
      name: "Текст (Mock)",
      description: "Тестовая текстовая модель",
    },
    pricing_rules: null,
  },
  {
    id: "m2",
    slug: "mock-image",
    modality: "image",
    provider: "mock",
    provider_model_id: "mock-image-v1",
    display_order: 20,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 5,
    capabilities: {
      aspect_ratios: ["1:1", "16:9", "9:16"],
      resolutions: ["720p", "1080p"],
      max_prompt_chars: 2000,
      supports_seed: true,
      ui: {
        simple_default: false,
        hidden_in_production: true,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "optional",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
    },
    localization: {
      name: "Изображение (Mock)",
      description: "Тестовая модель изображений",
    },
    pricing_rules: {
      resolution_multipliers: {
        "720p": { num: 1, den: 1 },
        "1080p": { num: 3, den: 2 },
      },
    },
  },
  {
    id: "m3",
    slug: "runway-gen4-image",
    modality: "image",
    provider: "runway",
    provider_model_id: "gen4_image",
    display_order: 40,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 8,
    capabilities: {
      aspect_ratios: ["1:1", "16:9", "9:16"],
      resolutions: ["720p", "1080p"],
      max_prompt_chars: 2000,
      supports_seed: true,
      ui: {
        simple_default: true,
        hidden_in_production: false,
        operation: "create",
        studio_tier: "pro",
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "optional",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
    },
    localization: {
      name: "Runway Gen-4 Image",
      description: "Изображения через Runway",
    },
    pricing_rules: null,
  },
  {
    id: "m4",
    slug: "runway-seedream5-lite-image",
    modality: "image",
    provider: "runway",
    provider_model_id: "seedream5_lite",
    display_order: 34,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 10,
    capabilities: {
      aspect_ratios: ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"],
      resolutions: ["2k", "3k"],
      max_prompt_chars: 4000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "create",
        studio_tier: "fast",
        smart_candidate: true,
        simple_default: true,
        hidden_in_production: false,
        eta_seconds: 25,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "forbidden",
      accepted_mime: [],
      max_input_bytes: 0,
      max_input_assets: 0,
    },
    localization: {
      name: "KELBET Fast",
      description: "Быстрый результат в высоком разрешении",
    },
    pricing_rules: null,
  },
  {
    id: "m5",
    slug: "runway-seedream5-pro-image",
    modality: "image",
    provider: "runway",
    provider_model_id: "seedream5_pro",
    display_order: 35,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 12,
    capabilities: {
      aspect_ratios: ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
      resolutions: ["1k", "2k", "auto_1k", "auto_2k"],
      max_prompt_chars: 4000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "create",
        studio_tier: "quality",
        smart_candidate: true,
        simple_default: false,
        hidden_in_production: false,
        eta_seconds: 45,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "forbidden",
      accepted_mime: [],
      max_input_bytes: 0,
      max_input_assets: 0,
    },
    localization: {
      name: "KELBET Quality",
      description: "Точная композиция и максимум деталей",
    },
    pricing_rules: {
      resolution_multipliers: {
        "1k": { num: 1, den: 1 },
        "2k": { num: 5, den: 3 },
        auto_1k: { num: 1, den: 1 },
        auto_2k: { num: 5, den: 3 },
      },
    },
  },
  {
    id: "m6",
    slug: "runway-seedream5-lite-edit",
    modality: "image_edit",
    provider: "runway",
    provider_model_id: "seedream5_lite",
    display_order: 36,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 10,
    capabilities: {
      aspect_ratios: ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"],
      resolutions: ["2k", "3k"],
      max_prompt_chars: 4000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "edit",
        studio_tier: "fast",
        smart_candidate: true,
        simple_default: true,
        hidden_in_production: false,
        eta_seconds: 30,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "required",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 10,
    },
    localization: {
      name: "KELBET Edit Fast",
      description: "Быстрое редактирование до 10 референсов",
    },
    pricing_rules: null,
  },
  {
    id: "m7",
    slug: "runway-seedream5-pro-edit",
    modality: "image_edit",
    provider: "runway",
    provider_model_id: "seedream5_pro",
    display_order: 37,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 12,
    capabilities: {
      aspect_ratios: ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
      resolutions: ["1k", "2k", "auto_1k", "auto_2k"],
      max_prompt_chars: 4000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "edit",
        studio_tier: "quality",
        smart_candidate: true,
        simple_default: false,
        hidden_in_production: false,
        eta_seconds: 50,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "required",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 10,
    },
    localization: {
      name: "KELBET Edit Quality",
      description: "Точное редактирование сложных сцен",
    },
    pricing_rules: {
      resolution_multipliers: {
        "1k": { num: 1, den: 1 },
        "2k": { num: 5, den: 3 },
        auto_1k: { num: 1, den: 1 },
        auto_2k: { num: 5, den: 3 },
      },
    },
  },
  {
    id: "m8",
    slug: "runway-magnific-image-upscale",
    modality: "upscale",
    provider: "runway",
    provider_model_id: "magnific_precision_upscaler_v2",
    display_order: 38,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 60,
    capabilities: {
      scale_factors: [2],
      flavors: ["photo", "photo_denoiser", "sublime"],
      defaults: {
        sharpen: 40,
        smart_grain: 20,
        ultra_detail: 50,
      },
      max_prompt_chars: 0,
      max_outputs: 1,
      ui: {
        operation: "upscale",
        studio_tier: "quality",
        simple_default: true,
        hidden_in_production: false,
        eta_seconds: 60,
      },
    },
    input_requirements: {
      prompt: "forbidden",
      source_image: "required",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
      max_input_width: 2048,
      max_input_height: 2048,
      require_known_dimensions: true,
    },
    localization: {
      name: "KELBET Upscale 2×",
      description: "Увеличение и восстановление деталей",
    },
    pricing_rules: null,
  },
  {
    id: "m9",
    slug: "runway-gemini-omni-video-fast",
    modality: "video",
    provider: "runway",
    provider_model_id: "gemini_omni_flash",
    display_order: 51,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 100,
    capabilities: {
      aspect_ratios: ["16:9", "9:16"],
      resolutions: ["720p"],
      durations_sec: [4, 8],
      max_prompt_chars: 1000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "video",
        studio_tier: "fast",
        smart_candidate: true,
        simple_default: true,
        hidden_in_production: false,
        eta_seconds: 180,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "optional",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
    },
    localization: {
      name: "KELBET Motion Fast",
      description: "Быстрые короткие ролики для ежедневного контента",
    },
    pricing_rules: {
      duration_multipliers: {
        "4": { num: 1, den: 1 },
        "8": { num: 2, den: 1 },
      },
    },
  },
  {
    id: "m10",
    slug: "runway-gen45-video-quality",
    modality: "video",
    provider: "runway",
    provider_model_id: "gen4.5",
    display_order: 52,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 120,
    capabilities: {
      aspect_ratios: ["16:9", "9:16"],
      resolutions: ["720p"],
      durations_sec: [4, 8],
      max_prompt_chars: 1000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "video",
        studio_tier: "quality",
        smart_candidate: true,
        simple_default: false,
        hidden_in_production: false,
        eta_seconds: 240,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "optional",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
    },
    localization: {
      name: "KELBET Motion Quality",
      description: "Точная камера и сложное движение в кадре",
    },
    pricing_rules: {
      duration_multipliers: {
        "4": { num: 1, den: 1 },
        "8": { num: 2, den: 1 },
      },
    },
  },
  {
    id: "m11",
    slug: "google-veo31-lite-video-fallback",
    modality: "video",
    provider: "google",
    provider_model_id: "veo-3.1-lite-generate-preview",
    display_order: 53,
    enabled: true,
    deprecated: false,
    replacement_slug: null,
    user_credit_price: 50,
    capabilities: {
      aspect_ratios: ["16:9", "9:16"],
      resolutions: ["720p"],
      durations_sec: [4, 6, 8],
      max_prompt_chars: 1000,
      supports_seed: false,
      max_outputs: 1,
      ui: {
        operation: "video",
        studio_tier: "alternative",
        smart_candidate: false,
        simple_default: false,
        hidden_in_production: false,
        eta_seconds: 360,
      },
    },
    input_requirements: {
      prompt: "required",
      source_image: "optional",
      accepted_mime: ["image/jpeg", "image/png", "image/webp"],
      max_input_bytes: 10_485_760,
      max_input_assets: 1,
    },
    localization: {
      name: "Google Veo 3.1 Lite",
      description: "Спокойные короткие сцены через Google Veo",
    },
    pricing_rules: {
      duration_multipliers: {
        "4": { num: 1, den: 1 },
        "6": { num: 3, den: 2 },
        "8": { num: 2, den: 1 },
      },
    },
  },
];

const generations = new Map<string, Generation>();
const quotes = new Map<string, Quote>();
const mockUploads = new Map<string, { file: File; status: "pending" | "ready" }>();
const mockAssets = new Map<string, AssetDownload>();
const promptAssistantResults = new Map<string, PromptAssistantResult>();
const generationByIdempotency = new Map<string, string>();
const simulatingGenerationIds = new Set<string>();
type StoredGenerationRequest = {
  modelSlug: string;
  prompt: string;
  params: Record<string, unknown>;
  inputAssetIds: string[];
  outputAssetIds: string[];
  templateId?: string | null;
  templateSlug?: string | null;
  templateVersion?: number | null;
  templateInputs?: Record<string, unknown>;
};
const MOCK_DRAFTS_KEY = "kelbet.mock.generation-drafts";
const MOCK_GENERATIONS_KEY = "kelbet.mock.generations";
const generationRequests = new Map<string, StoredGenerationRequest>();

function restoreGenerations(): void {
  try {
    const stored = JSON.parse(localStorage.getItem(MOCK_GENERATIONS_KEY) ?? "{}") as Record<
      string,
      Generation
    >;
    Object.entries(stored).forEach(([id, generation]) => generations.set(id, generation));
  } catch {
    localStorage.removeItem(MOCK_GENERATIONS_KEY);
  }
}

function persistGenerations(): void {
  localStorage.setItem(
    MOCK_GENERATIONS_KEY,
    JSON.stringify(Object.fromEntries(generations.entries())),
  );
}

function restoreGenerationRequests(): void {
  try {
    const stored = JSON.parse(localStorage.getItem(MOCK_DRAFTS_KEY) ?? "{}") as Record<
      string,
      StoredGenerationRequest
    >;
    Object.entries(stored).forEach(([id, request]) => generationRequests.set(id, request));
  } catch {
    localStorage.removeItem(MOCK_DRAFTS_KEY);
  }
}

function persistGenerationRequests(): void {
  localStorage.setItem(
    MOCK_DRAFTS_KEY,
    JSON.stringify(Object.fromEntries(generationRequests.entries())),
  );
}

restoreGenerations();
restoreGenerationRequests();

const seededReadyAssetId = "mock-history-ready-asset";
const seededReadyGenerationId = "mock-history-ready";
if (!generations.size) {
  mockAssets.set(seededReadyAssetId, {
    id: seededReadyAssetId,
    role: "output",
    content_type: "image/png",
    byte_size: 1_420_000,
    width: 1024,
    height: 1024,
    download_url: mockResultUrl,
    expires_in: 900,
  });
  [
    {
      id: seededReadyGenerationId,
      status: "succeeded",
      modality: "image",
      model_slug: "runway-gen4-image",
      template_slug: null,
      template_version: null,
      user_credit_price: 8,
      progress_pct: 100,
      progress_stage: "done",
      error_code: null,
      cancelable: false,
      reservation_id: null,
      output_asset_ids: [seededReadyAssetId],
      created_at: new Date(Date.now() - 34 * 60_000).toISOString(),
    },
    {
      id: "mock-history-active",
      status: "running",
      modality: "image",
      model_slug: "mock-image",
      template_slug: null,
      template_version: null,
      user_credit_price: 5,
      progress_pct: 62,
      progress_stage: "running",
      error_code: null,
      cancelable: true,
      reservation_id: "mock-history-active-reservation",
      output_asset_ids: [],
      created_at: new Date(Date.now() - 9 * 60_000).toISOString(),
    },
    {
      id: "mock-history-failed",
      status: "failed",
      modality: "image",
      model_slug: "runway-gen4-image",
      template_slug: null,
      template_version: null,
      user_credit_price: 8,
      progress_pct: 18,
      progress_stage: "failed",
      error_code: "provider_failed",
      cancelable: false,
      reservation_id: null,
      output_asset_ids: [],
      created_at: new Date(Date.now() - 26 * 60 * 60_000).toISOString(),
    },
  ].forEach((generation) => generations.set(generation.id, generation));
  generationRequests.set(seededReadyGenerationId, {
    modelSlug: "runway-gen4-image",
    prompt: "Editorial product portrait in warm morning light",
    params: { aspect_ratio: "1:1", resolution: "1080p" },
    inputAssetIds: [],
    outputAssetIds: [seededReadyAssetId],
  });
  persistGenerations();
  persistGenerationRequests();
}

function localizedModels(): CatalogModel[] {
  return models.map((model) => {
    if (model.slug === "mock-text") {
      return {
        ...model,
        localization: {
          name: language === "kk" ? "Мәтін (Mock)" : "Текст (Mock)",
          description:
            language === "kk" ? "Сынақ мәтін моделі" : "Тестовая текстовая модель",
        },
      };
    }
    if (model.slug === "mock-image") {
      return {
        ...model,
        localization: {
          name: language === "kk" ? "Сурет (Mock)" : "Изображение (Mock)",
          description:
            language === "kk" ? "Сынақ сурет моделі" : "Тестовая модель изображений",
        },
      };
    }
    const studioLocalization: Partial<
      Record<string, Record<Language, { name: string; description: string }>>
    > = {
      "runway-seedream5-lite-image": {
        ru: {
          name: "KELBET Fast",
          description: "Быстрый результат в высоком разрешении",
        },
        kk: {
          name: "KELBET Fast",
          description: "Жоғары ажыратымдылықтағы жылдам нәтиже",
        },
      },
      "runway-seedream5-pro-image": {
        ru: {
          name: "KELBET Quality",
          description: "Точная композиция и максимум деталей",
        },
        kk: {
          name: "KELBET Quality",
          description: "Дәл композиция және барынша көп деталь",
        },
      },
      "runway-seedream5-lite-edit": {
        ru: {
          name: "KELBET Edit Fast",
          description: "Быстрое редактирование до 10 референсов",
        },
        kk: {
          name: "KELBET Edit Fast",
          description: "10 референсқа дейін жылдам өңдеу",
        },
      },
      "runway-seedream5-pro-edit": {
        ru: {
          name: "KELBET Edit Quality",
          description: "Точное редактирование сложных сцен",
        },
        kk: {
          name: "KELBET Edit Quality",
          description: "Күрделі көріністерді дәл өңдеу",
        },
      },
      "runway-magnific-image-upscale": {
        ru: {
          name: "KELBET Upscale 2×",
          description: "Увеличение и восстановление деталей",
        },
        kk: {
          name: "KELBET Upscale 2×",
          description: "Үлкейту және детальдарды қалпына келтіру",
        },
      },
      "runway-gemini-omni-video-fast": {
        ru: {
          name: "KELBET Motion Fast",
          description: "Быстрые короткие ролики для ежедневного контента",
        },
        kk: {
          name: "KELBET Motion Fast",
          description: "Күнделікті контентке арналған жылдам қысқа роликтер",
        },
      },
      "runway-gen45-video-quality": {
        ru: {
          name: "KELBET Motion Quality",
          description: "Точная камера и сложное движение в кадре",
        },
        kk: {
          name: "KELBET Motion Quality",
          description: "Кадрдағы дәл камера және күрделі қозғалыс",
        },
      },
      "google-veo31-lite-video-fallback": {
        ru: {
          name: "KELBET Motion Reserve",
          description: "Резервный маршрут для восстановления сервиса",
        },
        kk: {
          name: "KELBET Motion Reserve",
          description: "Қызметті қалпына келтіруге арналған резервтік бағыт",
        },
      },
    };
    const localization = studioLocalization[model.slug]?.[language];
    if (localization) return { ...model, localization };
    return model;
  });
}

function me(): Me {
  return {
    id: "user-mock",
    telegram_id: 10001,
    username: "kelbet_demo",
    language,
    plan: "free",
    balance,
    reserved,
    available: balance - reserved,
    notify_generation_ready: notifyGenerationReady,
  };
}

/** Server-side style integer quote — client must never invent prices. */
const MOCK_TEMPLATE_SLUGS = new Map([
  ["22222222-2222-2222-2222-222222222201", "marketplace-product"],
  ["22222222-2222-2222-2222-222222222202", "cafe-promo"],
  ["22222222-2222-2222-2222-222222222203", "local-service-story"],
  ["22222222-2222-2222-2222-222222222204", "kazakh-fashion"],
  ["22222222-2222-2222-2222-222222222205", "real-estate"],
  ["22222222-2222-2222-2222-222222222206", "nauryz"],
  ["22222222-2222-2222-2222-222222222207", "kaspi-reveal"],
  ["22222222-2222-2222-2222-222222222208", "cafe-menu"],
  ["22222222-2222-2222-2222-222222222209", "property"],
  ["22222222-2222-2222-2222-222222222210", "toi"],
  ["22222222-2222-2222-2222-222222222211", "social-hook"],
]);

function serverQuote(
  modelSlug: string,
  params: Record<string, unknown>,
  template?: { templateId: string | null; templateInputs: Record<string, unknown> },
): Quote {
  const model = models.find((item) => item.slug === modelSlug);
  if (!model) {
    throw new Error("model_not_found");
  }
  let price = model.user_credit_price;
  const resolution = params.resolution;
  if (resolution === "1080p") {
    price = Math.ceil((price * 3) / 2);
  }
  if (
    (resolution === "2k" || resolution === "auto_2k") &&
    (modelSlug === "runway-seedream5-pro-image" ||
      modelSlug === "runway-seedream5-pro-edit")
  ) {
    price = Math.ceil((price * 5) / 3);
  }
  if (model.modality === "video" && params.duration_sec === 8) {
    price *= 2;
  }
  const canonicalTemplateInputs = Object.fromEntries(
    Object.entries(template?.templateInputs ?? {}).map(([key, value]) => [
      key,
      typeof value === "string" ? value.normalize("NFC").trim() : value,
    ]),
  );
  const quote: Quote = {
    quote_id: crypto.randomUUID(),
    model_slug: modelSlug,
    user_credit_price: price,
    currency: "credits",
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    params,
    template_id: template?.templateId ?? null,
    template_slug: template?.templateId
      ? MOCK_TEMPLATE_SLUGS.get(template.templateId) ?? null
      : null,
    template_version: template?.templateId ? 1 : null,
    template_inputs: canonicalTemplateInputs,
    available: balance - reserved,
  };
  quotes.set(quote.quote_id, quote);
  return quote;
}

export const mockApi = {
  async authTelegram(_initData: string): Promise<AuthResponse> {
    return {
      access_token: "mock-token",
      token_type: "bearer",
      expires_in: 3600,
      user: { id: "user-mock", language, plan: "free" },
    };
  },

  async getMe(): Promise<Me> {
    return me();
  },

  async getReferralSummary(): Promise<ReferralSummary> {
    return {
      enabled: true,
      code: "KELBETDEMO",
      link: "https://t.me/kelbet_demo_bot?start=ref_KELBETDEMO",
      invited_count: 4,
      pending_rewards_count: 1,
      credited_rewards_count: 2,
      credited_bonus_credits: 10,
      inviter_bonus_credits: 5,
      invitee_bonus_credits: 2,
      minimum_purchase_stars: 50,
      waiting_period_hours: 72,
    };
  },

  async patchMe(payload: {
    language?: Language;
    notify_generation_ready?: boolean;
  }): Promise<Me> {
    if (payload.language) {
      language = payload.language;
      try {
        localStorage.setItem(MOCK_PROFILE_LANGUAGE_KEY, language);
      } catch {
        // The in-memory mock remains functional when storage is unavailable.
      }
    }
    if (payload.notify_generation_ready !== undefined) {
      await delay(220);
      notifyGenerationReady = payload.notify_generation_ready;
    }
    return me();
  },

  async listPaymentProducts(): Promise<PaymentProducts> {
    const ru = language === "ru";
    return {
      payments_enabled: true,
      terms_url: "https://kelbet.ai/terms",
      terms_version: "2026-08-02-v1",
      refund_policy_url: "https://kelbet.ai/refunds",
      support_url: "https://t.me/kelbet_support",
      confirmation_note: "Credits arrive after Telegram confirms payment.",
      items: [
        {
          slug: "starter",
          name: ru ? "Старт" : "Бастау",
          description: ru ? "10 быстрых изображений или 1 короткое видео" : "10 жылдам сурет немесе 1 қысқа видео",
          credits: 100,
          stars: 100,
        },
        {
          slug: "creator",
          name: "Креатор",
          description: ru ? "Для регулярного контента" : "Тұрақты контентке арналған",
          credits: 300,
          stars: 270,
        },
        {
          slug: "studio",
          name: "Студия",
          description: ru ? "Для бизнеса и команд" : "Бизнес пен командаларға",
          credits: 800,
          stars: 640,
        },
      ],
    };
  },

  async createPaymentOrder(input: {
    productSlug: string;
    termsAccepted: boolean;
    termsVersion: string;
    idempotencyKey: string;
  }): Promise<PaymentOrder> {
    if (!input.termsAccepted) {
      throw new ApiError("payment_validation_error", "Terms required", 422);
    }
    const products = await this.listPaymentProducts();
    const product = products.items.find((item) => item.slug === input.productSlug);
    if (!product) {
      throw new ApiError("payment_product_not_found", "Product not found", 404);
    }
    const existing = paymentOrderRequests.get(input.idempotencyKey);
    if (existing) return existing;
    const id = crypto.randomUUID();
    const order: PaymentOrder = {
      id,
      status: "pending",
      product_slug: product.slug,
      product_name: product.name,
      credits: product.credits,
      currency: "XTR",
      total_amount: product.stars,
      invoice_url: `https://t.me/$kelbet_${id.replaceAll("-", "")}`,
      expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
      created_at: nowIso(),
      paid_at: null,
      refunded_at: null,
      refund_policy_url: products.refund_policy_url,
      support_url: products.support_url,
      support_reference: `KLB-${id.replaceAll("-", "").slice(0, 12).toUpperCase()}`,
    };
    paymentOrders.unshift(order);
    paymentOrderRequests.set(input.idempotencyKey, order);
    return order;
  },

  async reopenPaymentOrder(orderId: string): Promise<PaymentOrder> {
    const order = paymentOrders.find((item) => item.id === orderId);
    if (!order || order.status !== "pending") {
      throw new ApiError("payment_validation_error", "Order cannot be reopened", 422);
    }
    return {
      ...order,
      invoice_url: `https://t.me/$kelbet_${order.id.replaceAll("-", "")}`,
    };
  },

  async paymentHistory(): Promise<PaymentOrder[]> {
    return [...paymentOrders];
  },

  async listModels(): Promise<CatalogModel[]> {
    return localizedModels();
  },

  async listTemplates(
    _lang?: Language,
    _kind?: "image" | "video",
  ): Promise<GenerationTemplate[]> {
    // Pages provide the checked-in catalog only in explicit mock mode.
    return [];
  },

  async getModerationConfig(): Promise<ModerationConfig> {
    return {
      mode: "report",
      policy_version: "2026-08-01-v1",
      photo_rights_consent_version: "2026-08-01-v1",
      support_route: "/support",
      image_moderation_supported: false,
    };
  },

  async getModel(slug: string): Promise<CatalogModel> {
    const model = localizedModels().find((item) => item.slug === slug);
    if (!model) {
      throw new Error("not_found");
    }
    return model;
  },

  async quote(
    modelSlug: string,
    params: Record<string, unknown>,
    template?: { templateId: string | null; templateInputs: Record<string, unknown> },
  ): Promise<Quote> {
    await delay(180);
    return serverQuote(modelSlug, params, template);
  },

  async presignUpload(file: File): Promise<PresignedUpload> {
    await delay(120);
    const assetId = crypto.randomUUID();
    mockUploads.set(assetId, { file, status: "pending" });
    return {
      asset_id: assetId,
      upload_url: `mock://uploads/${assetId}`,
      object_key: `mock/input/${assetId}`,
      headers: { "Content-Type": file.type },
      expires_in: 900,
      max_bytes: 10_485_760,
    };
  },

  async completeUpload(assetId: string): Promise<CompletedUpload> {
    await delay(160);
    const upload = mockUploads.get(assetId);
    if (!upload) {
      throw new Error("upload_not_found");
    }
    const dimensions = await imageDimensions(upload.file);
    mockUploads.set(assetId, { ...upload, status: "ready" });
    mockAssets.set(assetId, {
      id: assetId,
      role: "input",
      content_type: upload.file.type,
      byte_size: upload.file.size,
      ...dimensions,
      download_url: URL.createObjectURL(upload.file),
      expires_in: 900,
    });
    return {
      asset_id: assetId,
      status: "ready",
      content_type: upload.file.type,
      byte_size: upload.file.size,
      magic_ok: true,
      ...dimensions,
    };
  },

  async uploadAsset(file: File): Promise<CompletedUpload> {
    const presigned = await this.presignUpload(file);
    return this.completeUpload(presigned.asset_id);
  },

  async getAsset(assetId: string): Promise<AssetDownload> {
    await delay(100);
    const storedRequest = [...generationRequests.values()].find((request) =>
      request.outputAssetIds.includes(assetId),
    );
    let asset = mockAssets.get(assetId);
    if (!asset && storedRequest) {
      const model = models.find((item) => item.slug === storedRequest.modelSlug);
      const isVideo = model?.modality === "video";
      const isVertical = storedRequest.params.aspect_ratio === "9:16";
      const videoBlob = isVideo ? await createMockVideoBlob(isVertical) : null;
      asset = {
        id: assetId,
        role: "output",
        content_type: videoBlob ? videoBlob.type : "image/png",
        byte_size: videoBlob?.size ?? 1_420_000,
        width: videoBlob ? (isVertical ? 360 : 640) : 1024,
        height: videoBlob ? (isVertical ? 640 : 360) : 1024,
        download_url: videoBlob ? URL.createObjectURL(videoBlob) : mockResultUrl,
        expires_in: 900,
      };
      mockAssets.set(assetId, asset);
    }
    if (!asset) {
      throw new Error("asset_not_found");
    }
    return asset;
  },

  async getAssets(assetIds: string[]): Promise<AssetDownload[]> {
    await delay(140);
    return Promise.all(assetIds.map((assetId) => this.getAsset(assetId)));
  },

  async getPromptAssistantConfig(): Promise<PromptAssistantConfig> {
    await delay(90);
    return {
      credit_cost: 1,
      max_input_chars: 1200,
      max_output_chars: 3000,
      charge_policy: "on_success",
    };
  },

  async improvePrompt(input: {
    brief: string;
    targetLanguage: Language;
    intent: PromptAssistantIntent;
    idempotencyKey: string;
  }): Promise<PromptAssistantResult> {
    const previous = promptAssistantResults.get(input.idempotencyKey);
    if (previous) return previous;
    const config = await this.getPromptAssistantConfig();
    if (!input.brief.trim()) {
      throw new ApiError("invalid_request", "Prompt is empty", 422);
    }
    if (input.brief.length > config.max_input_chars) {
      throw new ApiError("prompt_too_long", "Prompt is too long", 422);
    }
    if (balance < config.credit_cost) {
      throw new ApiError("insufficient_credits", "Not enough credits", 402);
    }
    await delay(650);
    const intentDetail: Record<PromptAssistantIntent, Record<Language, string>> = {
      general: {
        ru: "выразительная композиция, естественные материалы и выверенный визуальный ритм",
        kk: "мәнерлі композиция, табиғи материалдар және дәл визуалды ырғақ",
      },
      product: {
        ru: "премиальная предметная съёмка, чистая геометрия и деликатные блики",
        kk: "премиум заттық түсірілім, таза геометрия және нәзік жарық шағылысы",
      },
      social: {
        ru: "динамичный кадр для соцсетей, ясный фокус и место для короткого заголовка",
        kk: "әлеуметтік желіге арналған серпінді кадр, анық фокус және қысқа тақырыпқа орын",
      },
      portrait: {
        ru: "живой портрет, естественная фактура кожи и мягкий направленный свет",
        kk: "жанды портрет, терінің табиғи фактурасы және жұмсақ бағытталған жарық",
      },
      interior: {
        ru: "архитектурная глубина, тактильные поверхности и спокойный дневной свет",
        kk: "сәулеттік тереңдік, сезілетін беттер және тыныш күндізгі жарық",
      },
      food: {
        ru: "аппетитная фуд-съёмка, свежая текстура и тёплый боковой свет",
        kk: "тәбетті фуд-түсірілім, балғын текстура және жылы бүйір жарық",
      },
      fashion: {
        ru: "редакционная fashion-съёмка, пластичная поза и выразительный силуэт",
        kk: "редакциялық fashion-түсірілім, икемді қалып және мәнерлі силуэт",
      },
    };
    const improved =
      input.targetLanguage === "kk"
        ? `${input.brief.trim()}. ${intentDetail[input.intent].kk}. Қазақстандық заманауи визуал мәдениетіне жақын реңк, артық мәтінсіз, жоғары детализация, кадрда бөтен жазулар мен логотиптер жоқ.`
        : `${input.brief.trim()}. ${intentDetail[input.intent].ru}. Современная визуальная интонация Казахстана, без лишнего текста, высокая детализация, без случайных надписей и логотипов в кадре.`;
    balance -= config.credit_cost;
    const result: PromptAssistantResult = {
      improved_prompt: improved.slice(0, config.max_output_chars),
      language: input.targetLanguage,
      credit_cost: config.credit_cost,
      charged: true,
      balance,
      limits: {
        max_input_chars: config.max_input_chars,
        max_output_chars: config.max_output_chars,
      },
    };
    promptAssistantResults.set(input.idempotencyKey, result);
    return result;
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
    await delay(220);
    const existingId = generationByIdempotency.get(input.idempotencyKey);
    if (existingId) {
      const existing = generations.get(existingId);
      if (existing) return existing;
    }
    const quote = quotes.get(input.quoteId);
    if (!quote) {
      throw new Error("quote_not_found");
    }
    if (
      (input.templateId ?? null) !== quote.template_id ||
      JSON.stringify(input.templateInputs ?? {}) !== JSON.stringify(quote.template_inputs)
    ) {
      throw new ApiError("template_snapshot_mismatch", "Template snapshot mismatch", 409);
    }
    const model = models.find((item) => item.slug === quote.model_slug);
    const needsPhotoConsent =
      Boolean(input.inputAssetIds?.length) &&
      (model?.modality === "image_edit" || model?.modality === "video");
    if (
      needsPhotoConsent &&
      (!input.rightsConsentConfirmed || input.rightsConsentVersion !== "2026-08-01-v1")
    ) {
      throw new ApiError("photo_rights_consent_required", "Photo rights consent required", 422);
    }
    if (balance - reserved < quote.user_credit_price) {
      throw new Error("insufficient_credits");
    }
    for (const assetId of input.inputAssetIds ?? []) {
      if (mockUploads.get(assetId)?.status !== "ready" && !mockAssets.has(assetId)) {
        throw new Error("input_asset_not_ready");
      }
    }
    reserved += quote.user_credit_price;
    const id = crypto.randomUUID();
    const generation: Generation = {
      id,
      status: "queued",
      modality: models.find((m) => m.slug === quote.model_slug)?.modality ?? "text",
      model_slug: quote.model_slug,
      template_slug: quote.template_slug,
      template_version: quote.template_version,
      user_credit_price: quote.user_credit_price,
      progress_pct: 0,
      progress_stage: "queued",
      error_code: null,
      cancelable: true,
      reservation_id: crypto.randomUUID(),
      output_asset_ids: [],
      created_at: nowIso(),
    };
    generations.set(id, generation);
    generationByIdempotency.set(input.idempotencyKey, id);
    generationRequests.set(id, {
      modelSlug: quote.model_slug,
      prompt: input.prompt,
      params: { ...quote.params },
      inputAssetIds: [...(input.inputAssetIds ?? [])],
      outputAssetIds: [],
      templateId: quote.template_id,
      templateSlug: quote.template_slug,
      templateVersion: quote.template_version,
      templateInputs: { ...quote.template_inputs },
    });
    persistGenerations();
    persistGenerationRequests();
    startSimulation(id, quote.user_credit_price);
    return generation;
  },

  async getGeneration(id: string): Promise<Generation> {
    const generation = generations.get(id);
    if (!generation) {
      throw new Error("not_found");
    }
    if (["queued", "created", "submitting", "running", "finalizing"].includes(generation.status)) {
      startSimulation(id, generation.user_credit_price);
    }
    if (generation.status === "succeeded" && !generation.passport) {
      generation.passport = mockPassport(generation);
      persistGenerations();
    }
    return generation;
  },

  async getGenerationDraft(
    id: string,
    mode: GenerationDraftMode,
  ): Promise<GenerationDraft> {
    await delay(140);
    const source = generationRequests.get(id);
    if (!source) {
      throw new Error("not_found");
    }
    const requestedAssetIds =
      mode === "remix" || mode === "upscale"
        ? source.outputAssetIds.slice(0, 1)
        : source.inputAssetIds;
    const availableAssetIds = requestedAssetIds.filter((assetId) => {
      if (mode === "remix" || mode === "upscale") {
        return source.outputAssetIds.includes(assetId);
      }
      return mockUploads.get(assetId)?.status === "ready" || mockAssets.has(assetId);
    });
    const unavailableAssetIds = requestedAssetIds.filter(
      (assetId) => !availableAssetIds.includes(assetId),
    );
    const model = models.find((item) => item.slug === source.modelSlug);
    return {
      source_generation_id: id,
      mode,
      model_slug: source.modelSlug,
      modality: model?.modality ?? "image",
      prompt: source.prompt,
      params: { ...source.params },
      input_asset_ids: availableAssetIds,
      unavailable_asset_ids: unavailableAssetIds,
      missing_input_assets:
        unavailableAssetIds.length > 0
          ? unavailableAssetIds.length
          : (mode === "remix" || mode === "upscale") && availableAssetIds.length === 0
            ? 1
            : 0,
      model_available: Boolean(model?.enabled && !model.deprecated),
      replacement_slug: model?.replacement_slug ?? null,
      template_id: source.templateId ?? null,
      template_slug: source.templateSlug ?? null,
      template_version: source.templateVersion ?? null,
      template_inputs: { ...(source.templateInputs ?? {}) },
    };
  },

  async cancelGeneration(id: string): Promise<Generation> {
    const generation = generations.get(id);
    if (!generation) {
      throw new Error("not_found");
    }
    if (generation.cancelable && ["queued", "running", "submitting"].includes(generation.status)) {
      reserved = Math.max(0, reserved - generation.user_credit_price);
      const next: Generation = {
        ...generation,
        status: "cancelled",
        cancelable: false,
        progress_stage: "cancelled",
        error_code: "cancelled_by_user",
      };
      generations.set(id, next);
      persistGenerations();
      return next;
    }
    return generation;
  },

  async history(): Promise<HistoryItem[]> {
    return [...generations.values()]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((item) => ({
        id: item.id,
        status: item.status,
        modality: item.modality,
        model_slug: item.model_slug,
        user_credit_price: item.user_credit_price,
        progress_pct: item.progress_pct,
        output_asset_ids: item.output_asset_ids,
        preview_asset_id: item.output_asset_ids[0] ?? null,
        preview_content_type: item.output_asset_ids[0]
          ? mockAssets.get(item.output_asset_ids[0])?.content_type ?? "image/png"
          : null,
        created_at: item.created_at,
      }));
  },
};

/**
 * Паспорт для mock-режима. Значения выведены из самой работы, а подмена
 * маршрута выставляется детерминированно для части идентификаторов — иначе
 * раскрытие подмены нельзя было бы увидеть без живого фолбэка провайдера.
 */
function mockPassport(generation: Generation): GenerationPassport {
  const isVideo = generation.modality === "video";
  const fingerprint = generation.id.replace(/[^0-9a-f]/g, "").charCodeAt(0) || 0;
  const substituted = fingerprint % 3 === 0;
  const served = isVideo
    ? { provider: "google", model: "veo-3.1-fast" }
    : { provider: "google", model: "gemini-2.5-flash-image" };
  const requested = isVideo
    ? { provider: "runway", model: "gen4_turbo" }
    : { provider: "runway", model: "gen4_image" };
  const primary = substituted ? served : requested;
  return {
    provider: primary.provider,
    provider_model_id: primary.model,
    requested_provider: requested.provider,
    requested_provider_model_id: requested.model,
    substituted,
    credits_charged: generation.user_credit_price,
    attempts: substituted ? 2 : 1,
    aspect_ratio: isVideo ? "9:16" : "1:1",
    resolution: isVideo ? "720p" : "1024x1024",
    duration_sec: isVideo ? 8 : null,
    width: isVideo ? 720 : 1024,
    height: isVideo ? 1280 : 1024,
  };
}

function startSimulation(id: string, price: number): void {
  if (simulatingGenerationIds.has(id)) return;
  simulatingGenerationIds.add(id);
  void simulateProgress(id, price).finally(() => {
    simulatingGenerationIds.delete(id);
  });
}

async function simulateProgress(id: string, price: number): Promise<void> {
  await delay(700);
  const current = generations.get(id);
  if (!current || current.status === "cancelled") {
    return;
  }
  generations.set(id, {
    ...current,
    status: "running",
    progress_pct: 45,
    progress_stage: "running",
  });
  persistGenerations();
  await delay(900);
  const mid = generations.get(id);
  if (!mid || mid.status === "cancelled") {
    return;
  }
  reserved = Math.max(0, reserved - price);
  balance = Math.max(0, balance - price);
  const outputAssetId = crypto.randomUUID();
  const source = generationRequests.get(id);
  const modality = mid.modality;
  const isVertical = source?.params.aspect_ratio === "9:16";
  const videoBlob = modality === "video" ? await createMockVideoBlob(isVertical) : null;
  mockAssets.set(outputAssetId, {
    id: outputAssetId,
    role: "output",
    content_type: videoBlob ? videoBlob.type : "image/png",
    byte_size: videoBlob?.size ?? 1_420_000,
    width: videoBlob ? (isVertical ? 360 : 640) : 1024,
    height: videoBlob ? (isVertical ? 640 : 360) : 1024,
    download_url: videoBlob ? URL.createObjectURL(videoBlob) : mockResultUrl,
    expires_in: 900,
  });
  if (source) {
    generationRequests.set(id, { ...source, outputAssetIds: [outputAssetId] });
    persistGenerationRequests();
  }
  generations.set(id, {
    ...mid,
    status: "succeeded",
    progress_pct: 100,
    progress_stage: "done",
    cancelable: false,
    output_asset_ids: [outputAssetId],
  });
  persistGenerations();
}

async function createMockVideoBlob(isVertical: boolean): Promise<Blob | null> {
  if (!("MediaRecorder" in globalThis)) return null;
  const canvas = document.createElement("canvas");
  canvas.width = isVertical ? 360 : 640;
  canvas.height = isVertical ? 640 : 360;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const stream = canvas.captureStream(18);
  const mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
    ? "video/webm;codecs=vp8"
    : "video/webm";
  const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 900_000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data);
  };
  const completed = new Promise<Blob | null>((resolve) => {
    recorder.onerror = () => resolve(null);
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      resolve(chunks.length ? new Blob(chunks, { type: "video/webm" }) : null);
    };
  });
  const startedAt = performance.now();
  const draw = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / 1000);
    const width = canvas.width;
    const height = canvas.height;
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#061713");
    gradient.addColorStop(0.56, "#153a31");
    gradient.addColorStop(1, "#0b1c1a");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "rgba(216,195,161,0.36)";
    context.lineWidth = 1;
    for (let index = 0; index < 6; index += 1) {
      const offset = ((progress * width * 0.7 + index * 86) % (width + 120)) - 60;
      context.strokeRect(offset, height * 0.12, 58, height * 0.76);
    }
    context.fillStyle = "#d8c3a1";
    context.font = `700 ${Math.round(Math.min(width, height) * 0.055)}px Manrope`;
    context.letterSpacing = "3px";
    context.fillText("KELBET MOTION", width * 0.09, height * 0.84);
    context.fillStyle = "#3dcfb6";
    context.fillRect(width * (0.09 + progress * 0.68), height * 0.89, 8, 8);
    if (progress < 1) {
      requestAnimationFrame(draw);
    } else if (recorder.state !== "inactive") {
      recorder.stop();
    }
  };
  recorder.start();
  requestAnimationFrame(draw);
  return completed;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
