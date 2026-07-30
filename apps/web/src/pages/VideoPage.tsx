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
import type { CatalogModel } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { EmptyState } from "../shared/ui/EmptyState";
import { ErrorState } from "../shared/ui/ErrorState";
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

const VIDEO_RECIPES: VideoRecipe[] = [
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

export function VideoPage() {
  const { tx, language } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<SourcePhoto | null>(null);
  const hydratedRef = useRef(false);

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
  const [activeRecipe, setActiveRecipe] = useState<string | null>(null);
  const [continuation, setContinuation] = useState<"repeat" | "frame" | null>(null);
  const [clock, setClock] = useState(Date.now());

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
  const modelsQuery = useQuery({
    queryKey: ["catalog", language],
    queryFn: () => api.listModels(language),
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
            studioTier(model) !== "fallback" &&
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

  useEffect(() => {
    if (!selected) return;
    setParams((current) => compatibleParams(selected, current));
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

  const quoteQuery = useQuery({
    queryKey: ["quote", selected?.slug, params],
    queryFn: () => api.quote(selected!.slug, params),
    enabled: Boolean(selected),
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
      return api.createGeneration({
        quoteId: freshQuote.quote_id,
        prompt: prompt.trim(),
        idempotencyKey: crypto.randomUUID(),
        inputAssetIds: mode === "photo" && photo?.assetId ? [photo.assetId] : [],
      });
    },
    onSuccess: (generation) => {
      void navigate(`/generations/${generation.id}`);
    },
  });

  const clearPhoto = () => {
    setPhoto((current) => {
      if (current) revokeLocal(current.previewUrl);
      return null;
    });
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePhoto = async (event: ChangeEvent<HTMLInputElement>) => {
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

  const applyRecipe = (recipe: VideoRecipe) => {
    setActiveRecipe(recipe.id);
    setPrompt(recipe.prompt[language].slice(0, maxPromptChars));
    setParams((current) => ({
      ...current,
      aspect_ratio: recipe.aspectRatio,
      duration_sec: recipe.durationSec,
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
  if (!videoModels.length) return <EmptyState title={tx("video.noModels")} />;

  const submitDisabled =
    !selected ||
    !prompt.trim() ||
    !quote ||
    insufficient ||
    Boolean(photoPending) ||
    (mode === "photo" && !photoReady) ||
    createMutation.isPending;
  const selectedRecipe = VIDEO_RECIPES.find((recipe) => recipe.id === activeRecipe);

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
                  onClick={() => setMode(item)}
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
              <span>05 SCENES</span>
            </div>
            <div className="video-recipe-rail">
              {VIDEO_RECIPES.map((recipe, index) => (
                <button
                  key={recipe.id}
                  type="button"
                  className={activeRecipe === recipe.id ? "selected" : ""}
                  aria-pressed={activeRecipe === recipe.id}
                  onClick={() => applyRecipe(recipe)}
                >
                  <span className="video-recipe-number">{String(index + 1).padStart(2, "0")}</span>
                  <span className="video-recipe-marker" aria-hidden>{recipe.marker}</span>
                  <strong>{recipe.title[language]}</strong>
                  <small>{recipe.description[language]}</small>
                  <span className="video-recipe-meta">
                    {recipe.aspectRatio} · {recipe.durationSec}s
                  </span>
                </button>
              ))}
            </div>
          </section>

          <div className="video-film-rail" aria-label="Storyboard">
            {[
              activeRecipe ? "RECIPE" : "IDEA",
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
                className="visually-hidden"
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
                    <button type="button" onClick={() => fileInputRef.current?.click()}>
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
                  onClick={() => fileInputRef.current?.click()}
                >
                  <span aria-hidden>＋</span>
                  <strong>{tx("video.choosePhoto")}</strong>
                  <small>{tx("video.photoHelp")}</small>
                </button>
              )}
              {uploadError ? <p className="field-error">{uploadError}</p> : null}
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
                setPrompt(event.target.value);
                setActiveRecipe(null);
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
                      setParams((current) => ({ ...current, duration_sec: duration }))
                    }
                  >
                    <span>{String(duration).padStart(2, "0")}</span>
                    {tx("video.seconds")}
                  </button>
                ))}
              </div>
            </fieldset>
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
                <small>{tx("video.advancedHelp")}</small>
              </span>
              <span>{advanced ? "ON" : "OFF"}</span>
            </summary>
            <div className="video-advanced-body">
              <fieldset>
                <legend>{tx("video.model")}</legend>
                <div className="video-model-list">
                  {videoModels.map((model) => (
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
                        <strong>{model.localization.name}</strong>
                        <small>{model.slug}</small>
                      </span>
                      <b>{studioTier(model)}</b>
                    </button>
                  ))}
                </div>
              </fieldset>
              <div className="video-contract-line">
                <span>{tx("video.resolution")}</span>
                <strong>{resolutions[0] ?? "720p"}</strong>
              </div>
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

          <p className="video-refund-note">
            <span aria-hidden>↺</span>
            {tx("video.refund")}
          </p>

          <div className="video-quote-spacer" />
          <section className="video-quote" aria-live="polite">
            <div className="video-quote-copy">
              <span>
                {quoteSeconds > 0
                  ? `${tx("create.quoteLocked")} · ${quoteSeconds}s`
                  : tx("create.quoteExpired")}
              </span>
              <strong>
                {quoteQuery.isFetching
                  ? tx("create.quoteLoading")
                  : quote
                    ? `${quote.user_credit_price} cr`
                    : "—"}
              </strong>
              <small>
                {quote
                  ? `${tx("create.balanceAfter")}: ${remaining}`
                  : selectedRecipe?.title[language] ?? selected?.localization.name}
                {etaSeconds ? ` · ETA ~${Math.ceil(etaSeconds / 60)} min` : ""}
              </small>
            </div>
            <button
              type="button"
              className="btn video-submit"
              disabled={submitDisabled}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending
                ? tx("video.creating")
                : insufficient
                  ? tx("create.insufficient")
                  : quote
                    ? `${tx("video.submitWithPrice")} ${quote.user_credit_price}`
                    : tx("video.submit")}
              {!createMutation.isPending && !insufficient ? <span aria-hidden>→</span> : null}
            </button>
            {mode === "photo" && !photoReady && !photoPending ? (
              <p className="video-quote-error">{tx("video.photoRequired")}</p>
            ) : null}
            {quoteQuery.isError || createMutation.isError ? (
              <p className="video-quote-error">
                {tx("common.error")}{" "}
                {quoteQuery.isError ? (
                  <button type="button" onClick={() => void quoteQuery.refetch()}>
                    {tx("common.retry")}
                  </button>
                ) : null}
              </p>
            ) : null}
          </section>
        </aside>
      </div>
    </section>
  );
}
