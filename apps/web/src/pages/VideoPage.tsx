import { useMutation, useQuery } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, getApiMode } from "../shared/api/client";
import { PhotoRightsConsent } from "../features/moderation/PhotoRightsConsent";
import {
  idempotencyKeyForQuote,
  type SubmissionAttempt,
} from "../features/generation/submissionRecovery";
import {
  buildTemplateSelection,
  isTemplateUnavailable,
  templateFieldLabel,
  templateFieldsValid,
  templateMarker,
  templateSelectionFromQuote,
} from "../features/templates/selection";
import type { CatalogModel, GenerationTemplate, Language } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { EmptyState } from "../shared/ui/EmptyState";
import { ErrorState } from "../shared/ui/ErrorState";
import { GenerationRecovery } from "../shared/ui/GenerationRecovery";
import { SkeletonBlock } from "../shared/ui/Skeleton";

type VideoMode = "text" | "photo";
type PromiseTier = "smart" | "fast" | "quality";
type PhotoStatus = "uploading" | "ready" | "error";

type SourcePhoto = {
  assetId: string | null;
  previewUrl: string;
  status: PhotoStatus;
  width: number | null;
  height: number | null;
};

type VideoRecipe = {
  id: string;
  marker: string;
  title: { ru: string; kk: string };
  description: { ru: string; kk: string };
  prompt: { ru: string; kk: string };
  aspectRatio: "16:9" | "9:16";
  durationSec: 4 | 8;
};

const MOCK_VIDEO_RECIPES: VideoRecipe[] = [
  {
    id: "kaspi-reveal",
    marker: "K",
    title: { ru: "Kaspi product reveal", kk: "Kaspi тауар таныстырылымы" },
    description: {
      ru: "Карточка товара с ясным первым кадром",
      kk: "Тауар карточкасына арналған анық алғашқы кадр",
    },
    prompt: {
      ru: "Товар плавно появляется из темноты и поворачивается к камере, медленный точный наезд, чистый светлый фон, премиальные блики, короткий уверенный звуковой акцент",
      kk: "Тауар қараңғыдан біртіндеп көрініп, камераға бұрылады, баяу дәл жақындау, таза ашық фон, премиум жарық шағылысы, қысқа сенімді дыбыс екпіні",
    },
    aspectRatio: "9:16",
    durationSec: 4,
  },
  {
    id: "cafe-menu",
    marker: "C",
    title: { ru: "Кафе и меню", kk: "Кафе және мәзір" },
    description: {
      ru: "Аппетитный проход от детали к подаче",
      kk: "Детальдан ұсынуға дейінгі тәбетті өту",
    },
    prompt: {
      ru: "Камера скользит над свежим блюдом и останавливается на красивой подаче, лёгкий пар, тёплый боковой свет, уютная атмосфера алматинского кафе, тихий звон посуды",
      kk: "Камера жаңа тағамның үстімен сырғып, әдемі ұсынуда тоқтайды, жеңіл бу, жылы бүйір жарық, Алматы кафесінің жайлы атмосферасы, ыдыстың баяу сыңғыры",
    },
    aspectRatio: "9:16",
    durationSec: 4,
  },
  {
    id: "property",
    marker: "A",
    title: { ru: "Обзор недвижимости", kk: "Жылжымайтын мүлік шолуы" },
    description: {
      ru: "Спокойный проход по светлому интерьеру",
      kk: "Жарық интерьермен тыныш өту",
    },
    prompt: {
      ru: "Плавный проход камеры из гостиной к панорамному окну, естественный дневной свет, чистая архитектурная геометрия, спокойный дорогой ритм, мягкий городской фон",
      kk: "Камера қонақ бөлмеден панорамалық терезеге бірқалыпты өтеді, табиғи күндізгі жарық, таза сәулеттік геометрия, сабырлы премиум ырғақ, жұмсақ қала фоны",
    },
    aspectRatio: "16:9",
    durationSec: 8,
  },
  {
    id: "toi",
    marker: "T",
    title: { ru: "Той-приглашение", kk: "Тойға шақыру" },
    description: {
      ru: "Деликатное движение орнамента и света",
      kk: "Ою мен жарықтың нәзік қозғалысы",
    },
    prompt: {
      ru: "Золотистый казахский орнамент медленно раскрывается вокруг приглашения, мягкое движение ткани, вечерний песочный свет, торжественная спокойная атмосфера, далёкое звучание домбры",
      kk: "Алтын түсті қазақ оюы шақырудың айналасында баяу ашылады, матаның жұмсақ қозғалысы, кешкі құм түсті жарық, салтанатты тыныш атмосфера, алыстан естілген домбыра үні",
    },
    aspectRatio: "9:16",
    durationSec: 8,
  },
  {
    id: "social-hook",
    marker: "R",
    title: { ru: "Reels / TikTok hook", kk: "Reels / TikTok бастамасы" },
    description: {
      ru: "Контрастное действие в первую секунду",
      kk: "Алғашқы секундтағы контраст әрекет",
    },
    prompt: {
      ru: "Резкое выразительное действие в первом кадре, затем быстрый контролируемый отъезд камеры, высокий контраст, современный городской ритм Казахстана, короткий ударный звуковой переход",
      kk: "Алғашқы кадрда айқын тосын әрекет, кейін камераның жылдам әрі бақыланатын алыстауы, жоғары контраст, Қазақстан қаласының заманауи ырғағы, қысқа соқпалы дыбыстық өту",
    },
    aspectRatio: "9:16",
    durationSec: 4,
  },
];

const MOCK_VIDEO_TEMPLATE_IDS = [
  "22222222-2222-2222-2222-222222222207",
  "22222222-2222-2222-2222-222222222208",
  "22222222-2222-2222-2222-222222222209",
  "22222222-2222-2222-2222-222222222210",
  "22222222-2222-2222-2222-222222222211",
] as const;

function mockVideoTemplates(language: Language): GenerationTemplate[] {
  return MOCK_VIDEO_RECIPES.map((recipe, index) => ({
    id: MOCK_VIDEO_TEMPLATE_IDS[index]!,
    slug: recipe.id,
    version: 1,
    kind: "video",
    display_order: index + 100,
    localization: {
      name: recipe.title[language],
      description: recipe.description[language],
    },
    prompt_preset: recipe.prompt[language],
    aspect_ratio: recipe.aspectRatio,
    duration_sec: recipe.durationSec,
    compatible_modalities: ["video"],
    required_inputs: {
      assets: { min: 0, max: 1 },
      fields:
        recipe.id === "toi"
          ? [
              { key: "headline", type: "text", required: true, max_length: 80, label: language === "ru" ? "Имена или заголовок" : "Есімдер немесе тақырып" },
              { key: "body", type: "text", required: false, max_length: 120, label: language === "ru" ? "Приглашение" : "Шақыру мәтіні" },
              { key: "date", type: "text", required: true, max_length: 64, label: language === "ru" ? "Дата и время" : "Күні мен уақыты" },
              { key: "contact", type: "text", required: true, max_length: 80, label: language === "ru" ? "Место или контакт" : "Орын немесе байланыс" },
            ]
          : [],
    },
    preview_metadata: { marker: recipe.marker, source: "mock-local-v1" },
    compositor: recipe.id === "toi" ? "toi_invite_v1" : null,
  }));
}

const FALLBACK_MIME = ["image/jpeg", "image/png", "image/webp"];
const FALLBACK_MAX_BYTES = 10_485_760;

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function uiValue(model: CatalogModel, key: string): unknown {
  return recordValue(model.capabilities.ui)[key];
}

function stringOptions(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function numberOptions(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === "number" && Number.isFinite(item))
    : [];
}

function numericCapability(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function studioTier(model: CatalogModel): string {
  const value = uiValue(model, "studio_tier");
  return typeof value === "string" ? value : "";
}

function providerFamily(model: CatalogModel): "runway" | "google" | "other" {
  if (model.provider === "runway") return "runway";
  if (model.provider === "google") return "google";
  return "other";
}

function compatibleParams(
  model: CatalogModel,
  current: Record<string, unknown>,
): Record<string, unknown> {
  const aspects = stringOptions(model.capabilities.aspect_ratios);
  const resolutions = stringOptions(model.capabilities.resolutions);
  const durations = numberOptions(model.capabilities.durations_sec);
  const aspect =
    typeof current.aspect_ratio === "string" && aspects.includes(current.aspect_ratio)
      ? current.aspect_ratio
      : aspects[0] ?? "16:9";
  const resolution =
    typeof current.resolution === "string" && resolutions.includes(current.resolution)
      ? current.resolution
      : resolutions[0] ?? "720p";
  const duration =
    typeof current.duration_sec === "number" && durations.includes(current.duration_sec)
      ? current.duration_sec
      : durations[0] ?? 4;
  const next: Record<string, unknown> = {
    aspect_ratio: aspect,
    resolution,
    duration_sec: duration,
  };
  if (model.capabilities.supports_seed && Number.isInteger(current.seed)) {
    next.seed = current.seed;
  }
  return next;
}

function revokeLocal(url: string): void {
  if (url.startsWith("blob:")) URL.revokeObjectURL(url);
}

function isStaleQuoteError(error: unknown): boolean {
  return error instanceof Error && error.message === "stale_quote";
}

export function VideoPage() {
  const { tx, language } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<SourcePhoto | null>(null);
  const submissionRef = useRef<SubmissionAttempt | null>(null);
  const hydratedRef = useRef(false);
  const selectedModelRef = useRef<string | null>(null);

  const sourceGenerationId = searchParams.get("from")?.trim() ?? "";
  const sourceAssetId = searchParams.get("asset")?.trim() ?? "";
  const requestedMode = searchParams.get("mode");

  const [mode, setMode] = useState<VideoMode>(
    sourceAssetId || requestedMode === "photo" ? "photo" : "text",
  );
  const [promiseTier, setPromiseTier] = useState<PromiseTier>("smart");
  const [advanced, setAdvanced] = useState(false);
  const [explicitSlug, setExplicitSlug] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({
    aspect_ratio: "9:16",
    resolution: "720p",
    duration_sec: 4,
  });
  const [photo, setPhoto] = useState<SourcePhoto | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);
  const [restoredTemplateSlug, setRestoredTemplateSlug] = useState<string | null>(null);
  const [templateInputs, setTemplateInputs] = useState<Record<string, string>>({});
  const [continuation, setContinuation] = useState<"repeat" | "frame" | null>(null);
  const [clock, setClock] = useState(Date.now());
  const [rightsConsent, setRightsConsent] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [durationAdjusted, setDurationAdjusted] = useState(false);

  useEffect(() => {
    photoRef.current = photo;
  }, [photo]);

  useEffect(
    () => () => {
      if (photoRef.current) revokeLocal(photoRef.current.previewUrl);
    },
    [],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const moderationQuery = useQuery({
    queryKey: ["moderation", "config"],
    queryFn: () => api.getModerationConfig(),
    staleTime: 300_000,
  });
  const modelsQuery = useQuery({
    queryKey: ["catalog", language],
    queryFn: () => api.listModels(language),
  });
  const templatesQuery = useQuery({
    queryKey: ["catalog", "templates", language, "video"],
    queryFn: () =>
      getApiMode() === "mock"
        ? Promise.resolve(mockVideoTemplates(language))
        : api.listTemplates(language, "video"),
  });
  const draftQuery = useQuery({
    queryKey: ["generation-draft", sourceGenerationId, "repeat"],
    queryFn: () => api.getGenerationDraft(sourceGenerationId, "repeat"),
    enabled: Boolean(sourceGenerationId),
    retry: 1,
  });
  const sourceAssetQuery = useQuery({
    queryKey: ["asset", sourceAssetId],
    queryFn: () => api.getAsset(sourceAssetId),
    enabled: Boolean(sourceAssetId),
    retry: 1,
  });

  const videoModels = useMemo(
    () =>
      (modelsQuery.data ?? [])
        .filter(
          (model) =>
            model.modality === "video" &&
            model.enabled &&
            !model.deprecated &&
            uiValue(model, "operation") === "video" &&
            (getApiMode() === "mock" || !uiValue(model, "hidden_in_production")),
        )
        .sort((a, b) => a.display_order - b.display_order),
    [modelsQuery.data],
  );

  const promptSignals = prompt
    .trim()
    .split(/[,.—;]+/)
    .filter((part) => part.trim().length > 8).length;
  const smartResolvedTier: Exclude<PromiseTier, "smart"> =
    prompt.trim().length >= 260 || promptSignals >= 4 ? "quality" : "fast";
  const actualTier = promiseTier === "smart" ? smartResolvedTier : promiseTier;

  const selected = useMemo(() => {
    if (advanced && explicitSlug) {
      const explicit = videoModels.find((model) => model.slug === explicitSlug);
      if (explicit) return explicit;
    }
    return (
      videoModels.find(
        (model) =>
          studioTier(model) === actualTier && uiValue(model, "smart_candidate") !== false,
      ) ??
      videoModels.find((model) => studioTier(model) === actualTier) ??
      videoModels.find((model) => uiValue(model, "simple_default") === true) ??
      videoModels[0] ??
      null
    );
  }, [actualTier, advanced, explicitSlug, videoModels]);

  const videoTemplates = useMemo(
    () =>
      (templatesQuery.data ?? []).filter(
        (template) => !selected || template.compatible_modalities.includes(selected.modality),
      ),
    [selected, templatesQuery.data],
  );
  const activeTemplate = useMemo(
    () => videoTemplates.find((template) => template.id === activeTemplateId) ?? null,
    [activeTemplateId, videoTemplates],
  );
  const templateSelection = useMemo(
    () => buildTemplateSelection(activeTemplate, templateInputs),
    [activeTemplate, templateInputs],
  );
  const templateUnavailable = isTemplateUnavailable(
    activeTemplateId,
    activeTemplate,
    templatesQuery.isSuccess,
  );
  const templateValid =
    !templateUnavailable && templateFieldsValid(activeTemplate, templateInputs);

  useEffect(() => {
    if (!selected) return;
    setParams((current) => {
      const next = compatibleParams(selected, current);
      if (
        selectedModelRef.current &&
        selectedModelRef.current !== selected.slug &&
        current.duration_sec !== next.duration_sec
      ) {
        setDurationAdjusted(true);
      }
      return next;
    });
    selectedModelRef.current = selected.slug;
  }, [selected]);

  useEffect(() => {
    if (hydratedRef.current || !videoModels.length) return;
    const restore = async () => {
      if (sourceGenerationId && draftQuery.data) {
        hydratedRef.current = true;
        const draft = draftQuery.data;
        const original = videoModels.find((model) => model.slug === draft.model_slug);
        setPrompt(draft.prompt);
        setParams(original ? compatibleParams(original, draft.params) : draft.params);
        setActiveTemplateId(draft.template_id);
        setRestoredTemplateSlug(draft.template_slug);
        setTemplateInputs(
          Object.fromEntries(
            Object.entries(draft.template_inputs).flatMap(([key, value]) =>
              typeof value === "string" ? [[key, value]] : [],
            ),
          ),
        );
        if (original) {
          setAdvanced(true);
          setExplicitSlug(original.slug);
        }
        if (draft.input_asset_ids[0]) {
          try {
            const asset = await api.getAsset(draft.input_asset_ids[0]);
            setMode("photo");
            setPhoto({
              assetId: asset.id,
              previewUrl: asset.download_url,
              status: "ready",
              width: asset.width,
              height: asset.height,
            });
          } catch {
            setMode("photo");
          }
        }
        setContinuation("repeat");
        return;
      }
      if (sourceAssetId && sourceAssetQuery.data) {
        hydratedRef.current = true;
        const asset = sourceAssetQuery.data;
        setMode("photo");
        setPhoto({
          assetId: asset.id,
          previewUrl: asset.download_url,
          status: "ready",
          width: asset.width,
          height: asset.height,
        });
        setContinuation("frame");
      }
    };
    void restore();
  }, [
    draftQuery.data,
    sourceAssetId,
    sourceAssetQuery.data,
    sourceGenerationId,
    videoModels,
  ]);

  const acceptedMime = stringOptions(selected?.input_requirements.accepted_mime);
  const allowedMime = acceptedMime.length ? acceptedMime : FALLBACK_MIME;
  const maxInputBytes = numericCapability(
    selected?.input_requirements.max_input_bytes,
    FALLBACK_MAX_BYTES,
  );
  const maxPromptChars = numericCapability(selected?.capabilities.max_prompt_chars, 1000);
  const aspects = stringOptions(selected?.capabilities.aspect_ratios);
  const durations = numberOptions(selected?.capabilities.durations_sec);
  const resolutions = stringOptions(selected?.capabilities.resolutions);
  const etaSeconds = selected ? numericCapability(uiValue(selected, "eta_seconds"), 0) : 0;
  const extendedWorkflow = recordValue(selected?.capabilities.workflow).type === "veo_extend";
  const providerLabel =
    selected?.provider === "google"
      ? tx("video.providerGoogle")
      : selected?.provider === "runway"
        ? tx("video.providerRunway")
        : tx("video.providerStudio");

  const quoteEnabled = Boolean(selected) && templateValid && !templatesQuery.isLoading;
  const quoteQuery = useQuery({
    queryKey: ["quote", selected?.slug, params, templateSelection],
    queryFn: () => api.quote(selected!.slug, params, templateSelection),
    enabled: quoteEnabled,
    retry: 1,
  });
  const quote = quoteQuery.data;
  const quoteSeconds = quote
    ? Math.max(0, Math.floor((new Date(quote.expires_at).getTime() - clock) / 1000))
    : 0;
  const available = quote?.available ?? meQuery.data?.available ?? 0;
  const insufficient = Boolean(quote) && available < quote!.user_credit_price;
  const remaining = quote ? Math.max(0, available - quote.user_credit_price) : available;
  const photoReady = Boolean(photo?.status === "ready" && photo.assetId);
  const photoPending = photo?.status === "uploading";
  const templateAssetCount = photoReady && mode === "photo" ? 1 : 0;
  const templateAssetsValid = activeTemplate
    ? templateAssetCount >= activeTemplate.required_inputs.assets.min &&
      templateAssetCount <= activeTemplate.required_inputs.assets.max
    : true;

  const createMutation = useMutation({
    mutationFn: async () => {
      let freshQuote = quoteQuery.data;
      const secondsLeft = freshQuote
        ? (new Date(freshQuote.expires_at).getTime() - Date.now()) / 1000
        : 0;
      if (!freshQuote || secondsLeft <= 15) {
        const refreshed = await quoteQuery.refetch();
        freshQuote = refreshed.data;
      }
      if (!freshQuote || new Date(freshQuote.expires_at).getTime() <= Date.now()) {
        throw new Error("stale_quote");
      }
      const submission = idempotencyKeyForQuote(
        submissionRef.current,
        freshQuote.quote_id,
        JSON.stringify({
          prompt: prompt.trim(),
          inputAssetIds: mode === "photo" && photo?.assetId ? [photo.assetId] : [],
          rightsConsent: mode === "photo" && rightsConsent,
          template: templateSelectionFromQuote(freshQuote),
        }),
        () => crypto.randomUUID(),
      );
      submissionRef.current = submission;
      return api.createGeneration({
        quoteId: freshQuote.quote_id,
        prompt: prompt.trim(),
        idempotencyKey: submission.idempotencyKey,
        inputAssetIds: mode === "photo" && photo?.assetId ? [photo.assetId] : [],
        rightsConsentConfirmed: mode === "photo" && rightsConsent,
        rightsConsentVersion:
          mode === "photo" ? moderationQuery.data?.photo_rights_consent_version : undefined,
        ...templateSelectionFromQuote(freshQuote),
      });
    },
    onSuccess: (generation) => {
      void navigate(`/generations/${generation.id}`);
    },
  });

  const clearPhoto = () => {
    setSubmissionError(null);
    setRightsConsent(false);
    setPhoto((current) => {
      if (current) revokeLocal(current.previewUrl);
      return null;
    });
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePhoto = async (event: ChangeEvent<HTMLInputElement>) => {
    setSubmissionError(null);
    const file = event.target.files?.[0];
    if (!file) return;
    if (!allowedMime.includes(file.type)) {
      setUploadError(tx("video.invalidType"));
      event.target.value = "";
      return;
    }
    if (file.size > maxInputBytes) {
      setUploadError(tx("video.tooLarge"));
      event.target.value = "";
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    setRightsConsent(false);
    setUploadError(null);
    setPhoto((current) => {
      if (current) revokeLocal(current.previewUrl);
      return {
        assetId: null,
        previewUrl,
        status: "uploading",
        width: null,
        height: null,
      };
    });
    try {
      const presigned = await api.presignUpload(file);
      await api.uploadPresigned(presigned, file);
      const completed = await api.completeUpload(presigned.asset_id);
      setPhoto((current) =>
        current?.previewUrl === previewUrl
          ? {
              ...current,
              assetId: completed.asset_id,
              status: "ready",
              width: completed.width,
              height: completed.height,
            }
          : current,
      );
    } catch {
      setPhoto((current) =>
        current?.previewUrl === previewUrl ? { ...current, status: "error" } : current,
      );
      setUploadError(tx("video.uploadError"));
    }
  };

  const applyTemplate = (template: GenerationTemplate) => {
    setSubmissionError(null);
    if (activeTemplateId === template.id) {
      setActiveTemplateId(null);
      setRestoredTemplateSlug(null);
      setTemplateInputs({});
      return;
    }
    setActiveTemplateId(template.id);
    setRestoredTemplateSlug(template.slug);
    setTemplateInputs({});
    setPrompt(template.prompt_preset.slice(0, maxPromptChars));
    setParams((current) => ({
      ...current,
      aspect_ratio: aspects.includes(template.aspect_ratio)
        ? template.aspect_ratio
        : current.aspect_ratio,
      duration_sec:
        template.duration_sec && durations.includes(template.duration_sec)
          ? template.duration_sec
          : current.duration_sec,
    }));
  };

  const clearContinuation = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("from");
    next.delete("asset");
    next.delete("mode");
    setSearchParams(next, { replace: true });
    setContinuation(null);
  };

  if (modelsQuery.isLoading) return <SkeletonBlock rows={8} />;
  if (modelsQuery.isError) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void modelsQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }
  if (templatesQuery.isError) {
    return (
      <ErrorState
        title={language === "ru" ? "Не удалось загрузить каталог шаблонов" : "Үлгілер каталогы жүктелмеді"}
        onRetry={() => void templatesQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }
  if (!videoModels.length) return <EmptyState title={tx("video.noModels")} />;

  // React Query retains an earlier error while a refresh is in progress.
  // Keep the recovery panel hidden until that refresh has finished.
  const quoteRecoveryMode = !quoteEnabled || quoteQuery.isFetching
    ? null
    : quoteQuery.isError
      ? "quote"
      : (Boolean(quote) && quoteSeconds === 0) || isStaleQuoteError(createMutation.error)
        ? "expired"
        : createMutation.isError
          ? "submission"
          : null;

  const refreshQuote = () => {
    submissionRef.current = null;
    createMutation.reset();
    void quoteQuery.refetch();
  };

  const showSubmissionError = (message: string, selector?: string) => {
    setSubmissionError(message);
    if (selector) {
      window.requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(selector)?.focus();
      });
    }
  };

  const handleSubmit = () => {
    if (!selected) {
      showSubmissionError(tx("video.noModels"));
      return;
    }
    if (!prompt.trim()) {
      showSubmissionError(tx("video.promptRequired"), "#video-prompt");
      return;
    }
    if (photoPending) {
      showSubmissionError(tx("create.uploadsPending"), "[data-video-upload]");
      return;
    }
    if (mode === "photo" && !photoReady) {
      showSubmissionError(tx("video.photoRequired"), "[data-video-upload]");
      return;
    }
    if (!templateValid || !templateAssetsValid) {
      showSubmissionError(
        tx("create.templateRequired"),
        activeTemplate?.required_inputs.fields.length ? "[data-template-input]" : "[data-video-upload]",
      );
      return;
    }
    if (mode === "photo" && (!moderationQuery.data || !rightsConsent)) {
      showSubmissionError(tx("create.consentRequired"), "#video-photo-rights-check");
      return;
    }
    if (insufficient) {
      showSubmissionError(tx("create.insufficient"));
      return;
    }
    if (!quote || quoteSeconds === 0) {
      showSubmissionError(tx("create.quoteExpired"));
      if (!quoteQuery.isFetching) refreshQuote();
      return;
    }
    setSubmissionError(null);
    createMutation.mutate();
  };

  return (
    <section className="video-studio">
      <header className="studio-header video-studio-header rise">
        <div>
          <p className="eyebrow">KELBET MOTION ATELIER</p>
          <h1>{tx("video.title")}</h1>
          <p className="muted studio-subtitle">{tx("video.subtitle")}</p>
        </div>
        <div className="balance-pill" aria-label={tx("create.balance")}>
          <span className="balance-gem" aria-hidden />
          <strong>{meQuery.data?.available ?? "—"}</strong>
        </div>
      </header>

      {(sourceGenerationId && draftQuery.isLoading) ||
      (sourceAssetId && sourceAssetQuery.isLoading) ? (
        <div className="continuation-banner is-loading" role="status">
          <span className="continuation-mark" aria-hidden>▶</span>
          <p>{tx("video.restoring")}</p>
        </div>
      ) : null}
      {(sourceGenerationId && draftQuery.isError) ||
      (sourceAssetId && sourceAssetQuery.isError) ? (
        <div className="continuation-banner is-warning" role="alert">
          <span className="continuation-mark" aria-hidden>!</span>
          <div>
            <strong>{tx("video.restoreError")}</strong>
            <button
              type="button"
              onClick={() =>
                void (sourceGenerationId ? draftQuery.refetch() : sourceAssetQuery.refetch())
              }
            >
              {tx("common.retry")}
            </button>
          </div>
        </div>
      ) : null}
      {continuation ? (
        <div className="continuation-banner">
          <span className="continuation-mark" aria-hidden>
            {continuation === "frame" ? "▣" : "↻"}
          </span>
          <strong>
            {continuation === "frame"
              ? tx("video.fromFrameRestored")
              : tx("video.repeatRestored")}
          </strong>
          <button
            type="button"
            className="continuation-clear"
            aria-label={tx("video.clearContinuation")}
            onClick={clearContinuation}
          >
            ×
          </button>
        </div>
      ) : null}

      <div className="video-workspace">
        <div className="video-creative-column rise">
          <section className="video-mode-console" aria-labelledby="video-mode-title">
            <div className="video-section-rule">
              <span id="video-mode-title">01</span>
              <strong>{tx("video.modeLabel")}</strong>
            </div>
            <div className="video-mode-switch">
              {(["text", "photo"] as VideoMode[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={mode === item ? "selected" : ""}
                  aria-pressed={mode === item}
                  onClick={() => {
                    setSubmissionError(null);
                    if (item !== mode) setRightsConsent(false);
                    setMode(item);
                  }}
                >
                  <span aria-hidden>{item === "text" ? "Aa" : "▣"}</span>
                  <strong>{tx(item === "text" ? "video.textMode" : "video.photoMode")}</strong>
                  <small>{tx(item === "text" ? "video.textModeHelp" : "video.photoModeHelp")}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="video-recipe-section" aria-labelledby="video-recipes-title">
            <div className="video-recipe-heading">
              <div>
                <p className="eyebrow">{tx("video.recipesEyebrow")}</p>
                <h2 id="video-recipes-title">{tx("video.recipesTitle")}</h2>
              </div>
              <span>{String(videoTemplates.length).padStart(2, "0")} SCENES</span>
            </div>
            <div className="video-recipe-rail">
              {videoTemplates.map((template, index) => (
                <button
                  key={template.id}
                  type="button"
                  className={activeTemplateId === template.id ? "selected" : ""}
                  aria-pressed={activeTemplateId === template.id}
                  onClick={() => applyTemplate(template)}
                >
                  <span className="video-recipe-number">{String(index + 1).padStart(2, "0")}</span>
                  <span className="video-recipe-marker" aria-hidden>{templateMarker(template)}</span>
                  <strong>{template.localization.name}</strong>
                  <small>{template.localization.description}</small>
                </button>
              ))}
            </div>
            {templateUnavailable ? (
              <div className="continuation-banner is-warning" role="alert">
                <strong>
                  {language === "ru"
                    ? `Шаблон ${restoredTemplateSlug ?? ""} больше недоступен`
                    : `${restoredTemplateSlug ?? ""} үлгісі енді қолжетімсіз`}
                </strong>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTemplateId(null);
                    setRestoredTemplateSlug(null);
                    setTemplateInputs({});
                  }}
                >
                  {language === "ru" ? "Продолжить без шаблона" : "Үлгісіз жалғастыру"}
                </button>
              </div>
            ) : null}
            {activeTemplate?.required_inputs.fields.length ? (
              <div className="template-inputs" aria-label={language === "ru" ? "Данные шаблона" : "Үлгі деректері"}>
                {activeTemplate.required_inputs.fields.map((field) => (
                  <label key={field.key}>
                    <span>{templateFieldLabel(field, language)}{field.required ? " *" : ""}</span>
                    <input
                      data-template-input
                      type="text"
                      value={templateInputs[field.key] ?? ""}
                      maxLength={field.max_length}
                      required={field.required}
                      onChange={(event) =>
                        setTemplateInputs((current) => ({
                          ...current,
                          [field.key]: event.target.value,
                        }))
                      }
                    />
                    <small>{(templateInputs[field.key] ?? "").length}/{field.max_length}</small>
                  </label>
                ))}
              </div>
            ) : null}
          </section>

          <div className="video-film-rail" aria-label="Storyboard">
            {[
              activeTemplateId ? "RECIPE" : "IDEA",
              mode === "photo" ? "PHOTO" : "TEXT",
              String(params.aspect_ratio ?? "—"),
              `00:${String(params.duration_sec ?? 4).padStart(2, "0")}`,
            ].map((label, index) => (
              <span key={`${label}-${index}`} className={index < 3 || prompt ? "is-ready" : ""}>
                <b>{String(index + 1).padStart(2, "0")}</b>
                <i>{label}</i>
              </span>
            ))}
          </div>

          {mode === "photo" ? (
            <section className="video-photo-panel" aria-labelledby="video-photo-title">
              <input
                ref={fileInputRef}
                hidden
                type="file"
                accept={allowedMime.join(",")}
                onChange={handlePhoto}
              />
              <div className="video-section-rule">
                <span>02</span>
                <strong id="video-photo-title">{tx("video.photoTitle")}</strong>
              </div>
              {photo ? (
                <figure className={`video-photo-frame state-${photo.status}`}>
                  <div className="video-photo-preview">
                    <img src={photo.previewUrl} alt={tx("video.photoTitle")} />
                    <span className="video-frame-number">FRAME 01</span>
                    {photo.status === "uploading" ? <span className="video-photo-scan" /> : null}
                  </div>
                  <figcaption>
                    <div>
                      <strong>
                        {photo.status === "uploading"
                          ? tx("video.uploading")
                          : photo.status === "ready"
                            ? tx("video.uploadReady")
                            : tx("video.uploadError")}
                      </strong>
                      <small>
                        {photo.width && photo.height
                          ? `${photo.width}×${photo.height}`
                          : tx("video.photoHelp")}
                      </small>
                    </div>
                    <button
                      type="button"
                      data-video-upload
                      onClick={() => fileInputRef.current?.click()}
                    >
                      {tx("video.replacePhoto")}
                    </button>
                    <button type="button" onClick={clearPhoto}>
                      {tx("video.removePhoto")}
                    </button>
                  </figcaption>
                </figure>
              ) : (
                <button
                  type="button"
                  className="video-upload-zone"
                  data-video-upload
                  onClick={() => fileInputRef.current?.click()}
                >
                  <span aria-hidden>＋</span>
                  <strong>{tx("video.choosePhoto")}</strong>
                  <small>{tx("video.photoHelp")}</small>
                </button>
              )}
              {uploadError ? <p className="field-error">{uploadError}</p> : null}
              <PhotoRightsConsent
                id="video-photo-rights"
                language={language}
                config={moderationQuery.data}
                checked={rightsConsent}
                loading={moderationQuery.isLoading}
                error={moderationQuery.isError}
                onChange={(checked) => {
                  setSubmissionError(null);
                  setRightsConsent(checked);
                }}
              />
            </section>
          ) : null}

          <section className="video-prompt-panel" aria-labelledby="video-prompt-title">
            <div className="video-section-rule">
              <span>{mode === "photo" ? "03" : "02"}</span>
              <strong id="video-prompt-title">{tx("video.prompt")}</strong>
              <small>{prompt.length}/{maxPromptChars}</small>
            </div>
            <label className="visually-hidden" htmlFor="video-prompt">{tx("video.prompt")}</label>
            <textarea
              id="video-prompt"
              value={prompt}
              maxLength={maxPromptChars}
              placeholder={tx("video.promptHint")}
              onChange={(event) => {
                setSubmissionError(null);
                setPrompt(event.target.value);
              }}
            />
            <p className="video-prompt-guide">{tx("video.promptGuide")}</p>
          </section>
        </div>

        <aside className="video-controls-column">
          <section className="video-promise-console" aria-labelledby="video-promise-title">
            <div className="video-section-rule">
              <span>04</span>
              <strong id="video-promise-title">{tx("video.promiseLabel")}</strong>
              {etaSeconds ? <small>~{Math.ceil(etaSeconds / 60)} min</small> : null}
            </div>
            <div className="video-promise-switch">
              {(["smart", "fast", "quality"] as PromiseTier[]).map((tier) => (
                <button
                  key={tier}
                  type="button"
                  className={`${promiseTier === tier ? "selected" : ""} tier-${tier}`}
                  aria-pressed={promiseTier === tier}
                  onClick={() => {
                    setPromiseTier(tier);
                    setExplicitSlug(null);
                  }}
                >
                  <strong>{tx(`create.${tier}` as "create.smart")}</strong>
                  <small>{tx(`create.${tier}Help` as "create.smartHelp")}</small>
                </button>
              ))}
            </div>
            {promiseTier === "smart" ? (
              <p className="video-smart-note" aria-live="polite">
                <span aria-hidden />
                {tx(
                  smartResolvedTier === "quality"
                    ? "video.smartPickedQuality"
                    : "video.smartPickedFast",
                )}
              </p>
            ) : null}
          </section>

          <section className="video-simple-controls" aria-label={tx("create.settings")}>
            <fieldset>
              <legend>{tx("video.format")}</legend>
              <div className="video-option-row">
                {aspects.map((aspect) => (
                  <button
                    key={aspect}
                    type="button"
                    className={params.aspect_ratio === aspect ? "selected" : ""}
                    aria-pressed={params.aspect_ratio === aspect}
                    onClick={() => setParams((current) => ({ ...current, aspect_ratio: aspect }))}
                  >
                    <span className={`video-aspect-shape is-${aspect.replace(":", "-")}`} />
                    {aspect}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>{tx("video.duration")}</legend>
              <div className="video-option-row duration-options">
                {durations.map((duration) => (
                  <button
                    key={duration}
                    type="button"
                    className={params.duration_sec === duration ? "selected" : ""}
                    aria-pressed={params.duration_sec === duration}
                    onClick={() =>
                      {
                        setDurationAdjusted(false);
                        setParams((current) => ({ ...current, duration_sec: duration }));
                      }
                    }
                  >
                    <span>{String(duration).padStart(2, "0")}</span>
                    {duration === 29 && extendedWorkflow
                      ? tx("video.approxThirty")
                      : tx("video.seconds")}
                  </button>
                ))}
              </div>
            </fieldset>
            {durationAdjusted ? (
              <p className="video-compatibility-note" aria-live="polite">
                <span aria-hidden />
                {tx("video.durationAdjusted")}
              </p>
            ) : null}
            {extendedWorkflow ? (
              <p className="video-continuity-note">
                <span aria-hidden>LONG</span>
                {tx("video.extendedContinuity")}
              </p>
            ) : null}
          </section>

          <details
            className="video-advanced"
            open={advanced}
            onToggle={(event) => {
              setAdvanced(event.currentTarget.open);
              if (!event.currentTarget.open) setExplicitSlug(null);
            }}
          >
            <summary>
              <span className="pro-toggle-light" aria-hidden />
              <span>
                <strong>{tx("video.advanced")}</strong>
                <small>
                  {selected
                    ? `${selected.localization.name} · ${providerLabel}`
                    : tx("video.advancedHelp")}
                </small>
              </span>
              <span>{advanced ? tx("video.settingsOpen") : tx("video.settingsEdit")}</span>
            </summary>
            <div className="video-advanced-body">
              {selected ? (
                <article className="video-selected-model">
                  <div>
                    <span className={`video-provider-badge is-${providerFamily(selected)}`}>
                      {providerLabel}
                    </span>
                    {extendedWorkflow ? <span className="video-long-badge">LONG</span> : null}
                    <strong>{selected.localization.name}</strong>
                    <p>{selected.localization.description}</p>
                  </div>
                  <dl>
                    <div>
                      <dt>{tx("video.modelEta")}</dt>
                      <dd>{etaSeconds ? `~${Math.ceil(etaSeconds / 60)} ${tx("video.minutes")}` : "—"}</dd>
                    </div>
                    <div>
                      <dt>{tx("video.resolution")}</dt>
                      <dd>{String(params.resolution ?? resolutions[0] ?? "720p")}</dd>
                    </div>
                  </dl>
                </article>
              ) : null}
              <fieldset>
                <legend>{tx("video.model")}</legend>
                <div className="video-model-list">
                  {(["runway", "google", "other"] as const).map((family) => {
                    const familyModels = videoModels.filter(
                      (model) => providerFamily(model) === family,
                    );
                    if (!familyModels.length) return null;
                    const label =
                      family === "google"
                        ? tx("video.providerGoogle")
                        : family === "runway"
                          ? tx("video.providerRunway")
                          : tx("video.providerStudio");
                    return (
                      <section className="video-model-family" key={family}>
                        <h3>{label}</h3>
                        {familyModels.map((model) => (
                          <button
                            key={model.slug}
                            type="button"
                            className={selected?.slug === model.slug ? "selected" : ""}
                            onClick={() => {
                              setExplicitSlug(model.slug);
                              setParams((current) => compatibleParams(model, current));
                            }}
                          >
                            <span>
                              <strong>
                                {model.localization.name}
                                {recordValue(model.capabilities.workflow).type === "veo_extend" ? (
                                  <em className="video-model-long">LONG</em>
                                ) : null}
                              </strong>
                              <small>{model.localization.description}</small>
                            </span>
                            <b>{numericCapability(uiValue(model, "eta_seconds"), 0) ? `~${Math.ceil(numericCapability(uiValue(model, "eta_seconds"), 0) / 60)} ${tx("video.minutes")}` : ""}</b>
                          </button>
                        ))}
                      </section>
                    );
                  })}
                </div>
              </fieldset>
              {resolutions.length > 1 ? (
                <fieldset className="video-resolution-field">
                  <legend>{tx("video.resolution")}</legend>
                  <div className="video-option-row is-inline">
                    {resolutions.map((resolution) => (
                      <button
                        key={resolution}
                        type="button"
                        className={params.resolution === resolution ? "selected" : ""}
                        aria-pressed={params.resolution === resolution}
                        onClick={() =>
                          setParams((current) => ({ ...current, resolution }))
                        }
                      >
                        {resolution}
                      </button>
                    ))}
                  </div>
                </fieldset>
              ) : null}
              {selected?.capabilities.supports_seed ? (
                <label className="video-seed-field">
                  <span>{tx("video.seed")}</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    value={typeof params.seed === "number" ? params.seed : ""}
                    placeholder="Random"
                    onChange={(event) =>
                      setParams((current) => ({
                        ...current,
                        seed: event.target.value ? Number(event.target.value) : undefined,
                      }))
                    }
                  />
                </label>
              ) : null}
            </div>
          </details>

          <div className="video-quote-spacer" />
          <div className={`video-transaction-tray${quoteRecoveryMode ? " has-recovery" : ""}`}>
            {quoteRecoveryMode ? (
              <GenerationRecovery
                mode={quoteRecoveryMode}
                onAction={quoteRecoveryMode === "submission" ? () => createMutation.mutate() : refreshQuote}
              />
            ) : null}
            <section className="video-quote">
              <div className="video-quote-copy">
                <span>
                  {quoteSeconds > 0
                    ? `${tx("create.quoteLocked")} · ${quoteSeconds} ${tx("video.seconds")}`
                    : tx("create.quoteExpired")}
                </span>
                <strong>
                  {quoteQuery.isFetching
                    ? tx("create.quoteLoading")
                    : quote
                      ? `${quote.user_credit_price} ${tx("create.credits")}`
                      : "—"}
                </strong>
                <small>
                  {quote
                    ? `${tx("create.balanceAfter")}: ${remaining}`
                    : activeTemplate?.localization.name ?? selected?.localization.name}
                  {etaSeconds
                    ? ` · ${tx("create.eta")} ~${Math.ceil(etaSeconds / 60)} ${tx("video.minutes")}`
                    : ""}
                </small>
              </div>
              <button
                type="button"
                className="btn video-submit"
                disabled={createMutation.isPending}
                onClick={handleSubmit}
              >
                {createMutation.isPending
                  ? tx("video.creating")
                  : insufficient
                    ? tx("create.insufficient")
                    : quote
                      ? `${tx("video.submitWithPrice")} ${quote.user_credit_price} ${tx("create.credits")}`
                      : tx("video.submit")}
                {!createMutation.isPending && !insufficient ? <span aria-hidden>→</span> : null}
              </button>
              {mode === "photo" && !photoReady && !photoPending ? (
                <p className="video-quote-error">{tx("video.photoRequired")}</p>
              ) : null}
              {submissionError ? <p className="field-error" role="alert">{submissionError}</p> : null}
              <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
                {createMutation.isPending
                  ? tx("video.creating")
                  : quoteQuery.isFetching
                    ? tx("create.quoteLoading")
                    : ""}
              </div>
            </section>
          </div>
        </aside>
      </div>
    </section>
  );
}
