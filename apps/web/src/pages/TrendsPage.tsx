import { useMutation, useQuery } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  TREND_EDIT_SLUGS,
  TREND_TEMPLATES,
  TREND_VIDEO_SLUGS,
  type TrendKind,
  type TrendTemplate,
} from "../features/trends/templates";
import { PhotoRightsConsent } from "../features/moderation/PhotoRightsConsent";
import { api, getApiMode } from "../shared/api/client";
import type { CatalogModel } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { EmptyState } from "../shared/ui/EmptyState";
import { ErrorState } from "../shared/ui/ErrorState";
import { SkeletonBlock } from "../shared/ui/Skeleton";

type TrendFilter = "all" | TrendKind;
type PhotoStatus = "uploading" | "ready" | "error";

type PhotoItem = {
  localId: string;
  assetId: string | null;
  previewUrl: string;
  status: PhotoStatus;
};

const FALLBACK_MIME = ["image/jpeg", "image/png", "image/webp"];
const FALLBACK_MAX_BYTES = 10_485_760;

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

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function uiValue(model: CatalogModel, key: string): unknown {
  return recordValue(model.capabilities.ui)[key];
}

function usableModels(models: CatalogModel[]): CatalogModel[] {
  return models.filter(
    (model) =>
      model.enabled &&
      !model.deprecated &&
      (getApiMode() === "mock" || !uiValue(model, "hidden_in_production")),
  );
}

function pickModel(
  models: CatalogModel[],
  preferredSlugs: string[],
  modality: string,
): CatalogModel | null {
  for (const slug of preferredSlugs) {
    const match = models.find((model) => model.slug === slug);
    if (match) return match;
  }
  return (
    models
      .filter((model) => model.modality === modality)
      .sort((a, b) => a.display_order - b.display_order)[0] ?? null
  );
}

function trendParams(trend: TrendTemplate, model: CatalogModel): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  const aspects = stringOptions(model.capabilities.aspect_ratios);
  const resolutions = stringOptions(model.capabilities.resolutions);
  if (aspects.length) {
    params.aspect_ratio = aspects.includes(trend.aspectRatio)
      ? trend.aspectRatio
      : aspects[0];
  }
  if (resolutions.length) params.resolution = resolutions[0];
  if (trend.kind === "video") {
    const durations = numberOptions(model.capabilities.durations_sec);
    params.duration_sec =
      trend.durationSec && durations.includes(trend.durationSec)
        ? trend.durationSec
        : durations[0] ?? 4;
  }
  return params;
}

function revokeIfLocal(url: string): void {
  if (url.startsWith("blob:")) URL.revokeObjectURL(url);
}

export function TrendsPage() {
  const { tx, language } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const applyPanelRef = useRef<HTMLElement>(null);
  const photoRef = useRef<PhotoItem | null>(null);
  const hydratedTrendRef = useRef<string | null>(null);

  const trendParam = searchParams.get("trend")?.trim() ?? "";
  const [filter, setFilter] = useState<TrendFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [photo, setPhoto] = useState<PhotoItem | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [clock, setClock] = useState(Date.now());
  const [rightsConsent, setRightsConsent] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  useEffect(() => {
    photoRef.current = photo;
  }, [photo]);

  useEffect(
    () => () => {
      if (photoRef.current) revokeIfLocal(photoRef.current.previewUrl);
    },
    [],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!trendParam || hydratedTrendRef.current === trendParam) return;
    if (!TREND_TEMPLATES.some((trend) => trend.id === trendParam)) return;
    hydratedTrendRef.current = trendParam;
    setSelectedId(trendParam);
    window.setTimeout(() => {
      applyPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [trendParam]);

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

  const models = useMemo(() => usableModels(modelsQuery.data ?? []), [modelsQuery.data]);
  const editModel = useMemo(
    () => pickModel(models, TREND_EDIT_SLUGS, "image_edit"),
    [models],
  );
  const videoModel = useMemo(
    () => pickModel(models, TREND_VIDEO_SLUGS, "video"),
    [models],
  );

  const modelFor = (trend: TrendTemplate): CatalogModel | null =>
    trend.kind === "video" ? videoModel : editModel;

  const trends = TREND_TEMPLATES.filter(
    (trend) => (filter === "all" || trend.kind === filter) && Boolean(modelFor(trend)),
  );

  const selected = selectedId
    ? TREND_TEMPLATES.find((trend) => trend.id === selectedId) ?? null
    : null;
  const selectedModel = selected ? modelFor(selected) : null;
  const params = useMemo(
    () => (selected && selectedModel ? trendParams(selected, selectedModel) : {}),
    [selected, selectedModel],
  );

  const acceptedMime = stringOptions(selectedModel?.input_requirements.accepted_mime);
  const allowedMime = acceptedMime.length ? acceptedMime : FALLBACK_MIME;
  const maxInputBytes = numericCapability(
    selectedModel?.input_requirements.max_input_bytes,
    FALLBACK_MAX_BYTES,
  );

  const quoteQuery = useQuery({
    queryKey: ["quote", selectedModel?.slug, params],
    enabled: Boolean(selected && selectedModel),
    queryFn: () => api.quote(selectedModel!.slug, params),
    retry: 1,
  });

  const quote = quoteQuery.data;
  const quoteSeconds = quote
    ? Math.max(0, Math.floor((new Date(quote.expires_at).getTime() - clock) / 1000))
    : 0;
  const available = quote?.available ?? meQuery.data?.available ?? 0;
  const insufficient = Boolean(quote) && available < quote!.user_credit_price;
  const remaining = quote ? Math.max(0, available - quote.user_credit_price) : available;

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
        prompt: selected!.prompt,
        idempotencyKey: crypto.randomUUID(),
        inputAssetIds: photo?.assetId ? [photo.assetId] : [],
        rightsConsentConfirmed: rightsConsent,
        rightsConsentVersion: moderationQuery.data?.photo_rights_consent_version,
      });
    },
    onSuccess: (generation) => {
      void navigate(`/generations/${generation.id}`);
    },
  });

  const selectTrend = (trendId: string) => {
    setSubmissionError(null);
    setSelectedId(trendId);
    setUploadError(null);
    createMutation.reset();
    window.setTimeout(() => {
      applyPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  };

  const clearPhoto = () => {
    setSubmissionError(null);
    setRightsConsent(false);
    setPhoto((current) => {
      if (current) revokeIfLocal(current.previewUrl);
      return null;
    });
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const uploadPhoto = async (file: File) => {
    setSubmissionError(null);
    setRightsConsent(false);
    if (!allowedMime.includes(file.type)) {
      setUploadError(tx("create.invalidType"));
      return;
    }
    if (file.size > maxInputBytes) {
      setUploadError(tx("create.tooLarge"));
      return;
    }
    setUploadError(null);
    const localId = crypto.randomUUID();
    setPhoto((current) => {
      if (current) revokeIfLocal(current.previewUrl);
      return {
        localId,
        assetId: null,
        previewUrl: URL.createObjectURL(file),
        status: "uploading",
      };
    });
    try {
      const upload = await api.uploadAsset(file);
      setPhoto((current) =>
        current?.localId === localId
          ? { ...current, assetId: upload.asset_id, status: "ready" }
          : current,
      );
    } catch {
      setPhoto((current) =>
        current?.localId === localId ? { ...current, status: "error" } : current,
      );
    }
  };

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void uploadPhoto(file);
  };

  if (modelsQuery.isLoading) return <SkeletonBlock rows={7} />;
  if (modelsQuery.isError) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void modelsQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }
  if (!editModel && !videoModel) return <EmptyState title={tx("trends.noModels")} />;

  const photoReady = photo?.status === "ready" && Boolean(photo.assetId);
  const filters: Array<{ id: TrendFilter; label: string }> = [
    { id: "all", label: tx("trends.filterAll") },
    { id: "image", label: tx("trends.filterPhoto") },
    { id: "video", label: tx("trends.filterVideo") },
  ];

  const showSubmissionError = (message: string, selector?: string) => {
    setSubmissionError(message);
    if (selector) {
      window.requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(selector)?.focus();
      });
    }
  };

  const handleSubmit = () => {
    if (!selected || !selectedModel) {
      showSubmissionError(tx("trends.pickFirst"));
      return;
    }
    if (photo?.status === "uploading") {
      showSubmissionError(tx("create.uploadsPending"), "[data-trend-upload]");
      return;
    }
    if (!photoReady) {
      showSubmissionError(tx("trends.photoRequired"), "[data-trend-upload]");
      return;
    }
    if (!moderationQuery.data || !rightsConsent) {
      showSubmissionError(tx("create.consentRequired"), "#trend-photo-rights-check");
      return;
    }
    if (insufficient) {
      showSubmissionError(tx("create.insufficient"));
      return;
    }
    if (!quote || quoteSeconds === 0) {
      showSubmissionError(tx("create.quoteExpired"));
      if (!quoteQuery.isFetching) void quoteQuery.refetch();
      return;
    }
    setSubmissionError(null);
    createMutation.mutate();
  };

  return (
    <section className="create-studio trends-page">
      <header className="studio-header">
        <div>
          <p className="eyebrow">KELBET TREND LAB</p>
          <h1>{tx("trends.title")}</h1>
          <p className="muted studio-subtitle">{tx("trends.subtitle")}</p>
        </div>
        <div className="balance-pill" aria-label={tx("create.balance")}>
          <span className="balance-gem" aria-hidden />
          <strong>{meQuery.data?.available ?? "—"}</strong>
        </div>
      </header>

      <div className="trend-filter" role="group" aria-label={tx("trends.title")}>
        {filters.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            className={filter === item.id ? "selected" : ""}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
        <span className="trend-filter-meter" aria-hidden>
          {String(trends.length).padStart(2, "0")}
        </span>
      </div>

      <div className="trend-gallery" aria-label={tx("trends.galleryLabel")}>
        {trends.map((trend, index) => {
          const model = modelFor(trend);
          const active = selectedId === trend.id;
          return (
            <button
              key={trend.id}
              type="button"
              className={`trend-card${active ? " active" : ""}`}
              aria-pressed={active}
              onClick={() => selectTrend(trend.id)}
            >
              <span className="trend-visual">
                <img src={trend.preview} alt="" loading="lazy" decoding="async" />
                <i className="trend-kind">{trend.kind === "video" ? "MOTION" : "STILL"}</i>
                {trend.badge ? (
                  <i className={`trend-badge is-${trend.badge}`}>
                    {trend.badge === "hot" ? tx("trends.badgeHot") : tx("trends.badgeNew")}
                  </i>
                ) : null}
                <i className="trend-index">{String(index + 1).padStart(2, "0")}</i>
                {active ? <i className="trend-check">✓</i> : null}
              </span>
              <span className="trend-meta">
                <strong>{trend.title[language]}</strong>
                <small>{trend.description[language]}</small>
                <b>{model ? `${model.user_credit_price} cr` : "—"}</b>
              </span>
            </button>
          );
        })}
      </div>

      <input
        ref={fileInputRef}
        hidden
        type="file"
        accept={allowedMime.join(",")}
        onChange={handleFile}
      />

      {selected ? (
        <section
          ref={applyPanelRef}
          className="studio-panel trend-apply"
          aria-labelledby="trend-apply-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">{tx("trends.applyEyebrow")}</p>
              <h2 id="trend-apply-title">{selected.title[language]}</h2>
            </div>
            <span className="trend-apply-kind">
              {selected.kind === "video" ? "MOTION" : "STILL"}
            </span>
          </div>

          <div className="trend-apply-brief">
            <img src={selected.preview} alt="" loading="lazy" decoding="async" />
            <p>
              {selected.kind === "video"
                ? tx("trends.videoNote")
                : tx("trends.photoNote")}
            </p>
          </div>

          {photo ? (
            <div className={`trend-photo state-${photo.status}`}>
              <div className="trend-photo-frame">
                <img src={photo.previewUrl} alt={tx("trends.stepPhoto")} />
                {photo.status === "uploading" ? <span className="contact-scan" /> : null}
              </div>
              <footer>
                <div>
                  <strong>{tx("trends.stepPhoto")}</strong>
                  <small>
                    {photo.status === "uploading"
                      ? tx("create.uploading")
                      : photo.status === "error"
                        ? tx("create.uploadError")
                        : tx("trends.photoReady")}
                  </small>
                </div>
                <span className="trend-photo-actions">
                  <button
                    type="button"
                    data-trend-upload
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {tx("create.replacePhoto")}
                  </button>
                  <button
                    type="button"
                    aria-label={tx("create.removePhoto")}
                    onClick={clearPhoto}
                  >
                    ×
                  </button>
                </span>
              </footer>
            </div>
          ) : (
            <button
              type="button"
              className="upload-zone atelier-upload"
              data-trend-upload
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="upload-icon" aria-hidden>＋</span>
              <strong>{tx("trends.uploadTitle")}</strong>
              <span>{tx("trends.uploadHelp")}</span>
            </button>
          )}
          {uploadError ? <p className="field-error">{uploadError}</p> : null}
          <PhotoRightsConsent
            id="trend-photo-rights"
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

      <div className="create-action-spacer" />
      {selected ? (
        <aside className="create-action studio-quote" aria-live="polite">
          <div className="price-copy">
            <span>
              {quoteSeconds > 0
                ? `${tx("create.quoteLocked")} · ${quoteSeconds}s`
                : tx("create.quoteExpired")}
            </span>
            <strong>
              {quoteQuery.isFetching
                ? tx("create.quoteLoading")
                : quote
                  ? `${quote.user_credit_price} ${tx("create.credits")}`
                  : "—"}
            </strong>
            {quote ? <small>{tx("create.balanceAfter")}: {remaining}</small> : null}
          </div>
          <button
            type="button"
            className="btn create-submit"
            disabled={createMutation.isPending}
            onClick={handleSubmit}
          >
            {createMutation.isPending
              ? tx("create.creating")
              : insufficient
                ? tx("create.insufficient")
                : tx("trends.submit")}
            {!createMutation.isPending && !insufficient ? <span aria-hidden>→</span> : null}
          </button>
          {!photoReady && photo?.status !== "uploading" ? (
            <p className="action-hint">{tx("trends.photoRequired")}</p>
          ) : null}
          {submissionError ? <p className="field-error" role="alert">{submissionError}</p> : null}
          {quoteQuery.isError ? (
            <p className="field-error">
              {tx("create.quoteError")}{" "}
              <button type="button" onClick={() => void quoteQuery.refetch()}>
                {tx("common.retry")}
              </button>
            </p>
          ) : null}
          {createMutation.isError ? <p className="field-error">{tx("common.error")}</p> : null}
        </aside>
      ) : (
        <aside className="create-action studio-quote trend-pick-hint">
          <div className="price-copy">
            <span>KELBET TREND LAB</span>
            <strong>{tx("trends.pickFirst")}</strong>
          </div>
        </aside>
      )}
    </section>
  );
}
