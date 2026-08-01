import { useMutation, useQuery } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type SyntheticEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PromptAssistant } from "../features/create/PromptAssistant";
import { mockImageTemplates } from "../features/create/templates";
import { PhotoRightsConsent } from "../features/moderation/PhotoRightsConsent";
import {
  buildTemplateSelection,
  isTemplateUnavailable,
  templateFieldLabel,
  templateFieldsValid,
  templateMarker,
  templateSelectionFromQuote,
} from "../features/templates/selection";
import { api, getApiMode } from "../shared/api/client";
import type {
  CatalogModel,
  GenerationDraftMode,
} from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { EmptyState } from "../shared/ui/EmptyState";
import { ErrorState } from "../shared/ui/ErrorState";
import { SkeletonBlock } from "../shared/ui/Skeleton";

type Operation = "create" | "edit" | "upscale";
type PromiseTier = "smart" | "fast" | "quality";
type StudioMode = "simple" | "advanced";
type ReferenceStatus = "uploading" | "ready" | "error";

type ReferenceItem = {
  localId: string;
  assetId: string | null;
  previewUrl: string;
  status: ReferenceStatus;
  width: number | null;
  height: number | null;
};

type ContinuationNotice = {
  mode: GenerationDraftMode;
  missingReferences: number;
  modelChanged: boolean;
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

function operationFor(model: CatalogModel): Operation | null {
  const explicit = uiValue(model, "operation");
  if (explicit === "create" || explicit === "edit" || explicit === "upscale") return explicit;
  if (model.modality === "image") return "create";
  if (model.modality === "image_edit") return "edit";
  if (model.modality === "upscale") return "upscale";
  return null;
}

function studioTier(model: CatalogModel): string {
  const value = uiValue(model, "studio_tier");
  return typeof value === "string" ? value : "";
}

function compatibleParams(
  model: CatalogModel,
  operation: Operation,
  current: Record<string, unknown> = {},
): Record<string, unknown> {
  if (operation === "upscale") {
    const defaults = recordValue(model.capabilities.defaults);
    const flavors = stringOptions(model.capabilities.flavors);
    const scales = numberOptions(model.capabilities.scale_factors);
    const flavor =
      typeof current.flavor === "string" && flavors.includes(current.flavor)
        ? current.flavor
        : typeof defaults.flavor === "string" && flavors.includes(defaults.flavor)
          ? defaults.flavor
          : flavors[0] ?? "photo";
    const scale = numericCapability(defaults.scale_factor, scales[0] ?? 2);
    return {
      flavor,
      scale_factor: scale,
      sharpen: numericCapability(current.sharpen, numericCapability(defaults.sharpen, 45)),
      smart_grain: numericCapability(
        current.smart_grain,
        numericCapability(defaults.smart_grain, 25),
      ),
      ultra_detail: numericCapability(
        current.ultra_detail,
        numericCapability(defaults.ultra_detail, 55),
      ),
    };
  }

  const resolutions = stringOptions(model.capabilities.resolutions);
  const aspects = stringOptions(model.capabilities.aspect_ratios);
  const next: Record<string, unknown> = {};
  const resolution =
    typeof current.resolution === "string" && resolutions.includes(current.resolution)
      ? current.resolution
      : resolutions[0];
  const aspect =
    typeof current.aspect_ratio === "string" && aspects.includes(current.aspect_ratio)
      ? current.aspect_ratio
      : aspects[0];
  if (resolution) next.resolution = resolution;
  if (aspect) next.aspect_ratio = aspect;
  if (model.capabilities.supports_seed && Number.isInteger(current.seed)) {
    next.seed = current.seed;
  }
  return next;
}

function revokeIfLocal(url: string): void {
  if (url.startsWith("blob:")) URL.revokeObjectURL(url);
}

export function CreatePage() {
  const { tx, language } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const referencesRef = useRef<ReferenceItem[]>([]);
  const hydratedKeyRef = useRef<string | null>(null);
  const recipeHydratedRef = useRef<string | null>(null);

  const sourceId = searchParams.get("from")?.trim() ?? "";
  const modeParam = searchParams.get("mode");
  const taskParam = searchParams.get("task");
  const recipeParam = searchParams.get("recipe")?.trim() ?? "";
  const draftMode: GenerationDraftMode =
    taskParam === "upscale" || modeParam === "upscale"
      ? "upscale"
      : modeParam === "remix"
        ? "remix"
        : "repeat";
  const draftKey = sourceId ? `${sourceId}:${draftMode}` : "";

  const [operation, setOperation] = useState<Operation>(
    draftMode === "upscale" ? "upscale" : "create",
  );
  const [promiseTier, setPromiseTier] = useState<PromiseTier>("smart");
  const [studioMode, setStudioMode] = useState<StudioMode>("simple");
  const [explicitSlug, setExplicitSlug] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [references, setReferences] = useState<ReferenceItem[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);
  const [restoredTemplateSlug, setRestoredTemplateSlug] = useState<string | null>(null);
  const [templateInputs, setTemplateInputs] = useState<Record<string, string>>({});
  const [continuation, setContinuation] = useState<ContinuationNotice | null>(null);
  const [clock, setClock] = useState(Date.now());
  const [rightsConsent, setRightsConsent] = useState(false);

  useEffect(() => {
    referencesRef.current = references;
  }, [references]);

  useEffect(
    () => () => {
      referencesRef.current.forEach((item) => revokeIfLocal(item.previewUrl));
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
    queryKey: ["catalog", "templates", language, "image"],
    queryFn: async () => {
      if (getApiMode() === "mock") return mockImageTemplates(language);
      return api.listTemplates(language, "image");
    },
  });
  const draftQuery = useQuery({
    queryKey: ["generation-draft", sourceId, draftMode],
    queryFn: () => api.getGenerationDraft(sourceId, draftMode),
    enabled: Boolean(sourceId),
    retry: 1,
  });

  const studioModels = useMemo(
    () =>
      (modelsQuery.data ?? [])
        .filter(
          (model) =>
            model.enabled &&
            !model.deprecated &&
            operationFor(model) &&
            (getApiMode() === "mock" || !uiValue(model, "hidden_in_production")),
        )
        .sort((a, b) => a.display_order - b.display_order),
    [modelsQuery.data],
  );

  const operationModels = useMemo(
    () => studioModels.filter((model) => operationFor(model) === operation),
    [operation, studioModels],
  );

  const smartResolvedTier: Exclude<PromiseTier, "smart"> =
    prompt.trim().length >= 600 ||
    (operation === "edit" && references.filter((item) => item.status !== "error").length >= 4)
      ? "quality"
      : "fast";
  const actualTier = promiseTier === "smart" ? smartResolvedTier : promiseTier;

  const selected = useMemo(() => {
    if (studioMode === "advanced" && explicitSlug) {
      const explicit = operationModels.find((model) => model.slug === explicitSlug);
      if (explicit) return explicit;
    }
    if (operation === "upscale") return operationModels[0] ?? null;
    return (
      operationModels.find(
        (model) =>
          studioTier(model) === actualTier && uiValue(model, "smart_candidate") !== false,
      ) ??
      operationModels.find((model) => studioTier(model) === actualTier) ??
      operationModels[0] ??
      null
    );
  }, [actualTier, explicitSlug, operation, operationModels, studioMode]);

  const imageTemplates = useMemo(
    () =>
      (templatesQuery.data ?? []).filter(
        (template) => !selected || template.compatible_modalities.includes(selected.modality),
      ),
    [selected, templatesQuery.data],
  );
  const activeTemplate = useMemo(
    () =>
      (templatesQuery.data ?? []).find((template) => template.id === activeTemplateId) ?? null,
    [activeTemplateId, templatesQuery.data],
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
    setParams((current) => compatibleParams(selected, operation, current));
  }, [operation, selected]);

  useEffect(() => {
    const draft = draftQuery.data;
    if (!draft || !draftKey || hydratedKeyRef.current === draftKey || !studioModels.length) return;
    hydratedKeyRef.current = draftKey;
    let cancelled = false;

    const restore = async () => {
      const restoredOperation: Operation =
        draft.mode === "upscale"
          ? "upscale"
          : draft.mode === "remix"
            ? "edit"
            : draft.modality === "image_edit"
              ? "edit"
              : draft.modality === "upscale"
                ? "upscale"
                : "create";
      const eligible = studioModels.filter((model) => operationFor(model) === restoredOperation);
      const original = eligible.find((model) => model.slug === draft.model_slug) ?? null;
      const replacement = eligible.find((model) => model.slug === draft.replacement_slug) ?? null;
      const chosen = draft.model_available && original ? original : replacement;

      setOperation(restoredOperation);
      setStudioMode(chosen ? "advanced" : "simple");
      setExplicitSlug(chosen?.slug ?? null);
      setPrompt(restoredOperation === "upscale" ? "" : draft.prompt);
      setParams(chosen ? compatibleParams(chosen, restoredOperation, draft.params) : draft.params);
      setActiveTemplateId(draft.template_id);
      setRestoredTemplateSlug(draft.template_slug);
      setTemplateInputs(
        Object.fromEntries(
          Object.entries(draft.template_inputs).flatMap(([key, value]) =>
            typeof value === "string" ? [[key, value]] : [],
          ),
        ),
      );

      let restored: ReferenceItem[] = [];
      if (draft.input_asset_ids.length) {
        try {
          const assets = await api.getAssets(draft.input_asset_ids);
          const byId = new Map(assets.map((asset) => [asset.id, asset]));
          restored = draft.input_asset_ids.flatMap((id) => {
            const asset = byId.get(id);
            return asset
              ? [
                  {
                    localId: `restored-${id}`,
                    assetId: id,
                    previewUrl: asset.download_url,
                    status: "ready" as const,
                    width: asset.width,
                    height: asset.height,
                  },
                ]
              : [];
          });
        } catch {
          restored = [];
        }
      }
      if (cancelled) return;
      setReferences((current) => {
        current.forEach((item) => revokeIfLocal(item.previewUrl));
        return restored;
      });
      setContinuation({
        mode: draft.mode,
        missingReferences:
          draft.missing_input_assets + Math.max(0, draft.input_asset_ids.length - restored.length),
        modelChanged: Boolean(
          draft.mode === "repeat" && draft.model_slug && chosen?.slug !== draft.model_slug,
        ),
      });
    };

    void restore();
    return () => {
      cancelled = true;
    };
  }, [draftKey, draftQuery.data, studioModels]);

  const modelMaxReferences = numericCapability(
    selected?.input_requirements.max_input_assets,
    operation === "edit" ? 10 : operation === "upscale" ? 1 : 0,
  );
  const modelMinReferences = numericCapability(
    selected?.input_requirements.min_input_assets,
    operation === "create" ? 0 : 1,
  );
  const maxReferences = activeTemplate
    ? Math.min(modelMaxReferences, activeTemplate.required_inputs.assets.max)
    : modelMaxReferences;
  const minReferences = activeTemplate
    ? Math.max(modelMinReferences, activeTemplate.required_inputs.assets.min)
    : modelMinReferences;
  const acceptedMime = stringOptions(selected?.input_requirements.accepted_mime);
  const allowedMime = acceptedMime.length ? acceptedMime : FALLBACK_MIME;
  const maxInputBytes = numericCapability(
    selected?.input_requirements.max_input_bytes,
    FALLBACK_MAX_BYTES,
  );
  const upscaleMaxWidth = numericCapability(
    selected?.input_requirements.max_input_width,
    2048,
  );
  const upscaleMaxHeight = numericCapability(
    selected?.input_requirements.max_input_height,
    2048,
  );
  const requireKnownDimensions =
    selected?.input_requirements.require_known_dimensions !== false;
  const maxPromptChars = numericCapability(selected?.capabilities.max_prompt_chars, 2000);
  const resolutions = stringOptions(selected?.capabilities.resolutions);
  const aspects = stringOptions(selected?.capabilities.aspect_ratios);
  const flavors = stringOptions(selected?.capabilities.flavors);
  const etaSeconds = selected
    ? numericCapability(uiValue(selected, "eta_seconds"), 0)
    : 0;

  const quoteQuery = useQuery({
    queryKey: ["quote", selected?.slug, params, templateSelection],
    enabled: Boolean(selected) && templateValid && !templatesQuery.isLoading,
    queryFn: () => api.quote(selected!.slug, params, templateSelection),
    retry: 1,
  });

  const quote = quoteQuery.data;
  const quoteSeconds = quote
    ? Math.max(0, Math.floor((new Date(quote.expires_at).getTime() - clock) / 1000))
    : 0;
  const available = quote?.available ?? meQuery.data?.available ?? 0;
  const insufficient = Boolean(quote) && available < quote!.user_credit_price;
  const remaining = quote ? Math.max(0, available - quote.user_credit_price) : available;
  const readyReferences = references.filter(
    (item): item is ReferenceItem & { assetId: string } =>
      item.status === "ready" && Boolean(item.assetId),
  );
  const uploadsPending = references.some((item) => item.status === "uploading");
  const referencesMissing = readyReferences.length < minReferences;
  const referencesOverLimit = readyReferences.length > maxReferences;
  const upscaleSource = operation === "upscale" ? readyReferences[0] : undefined;
  const upscaleDimensionsKnown = Boolean(upscaleSource?.width && upscaleSource.height);
  const upscaleTooLarge = Boolean(
    upscaleSource &&
      upscaleDimensionsKnown &&
      (upscaleSource.width! > upscaleMaxWidth || upscaleSource.height! > upscaleMaxHeight),
  );
  const upscaleBlocked = operation === "upscale" && Boolean(upscaleSource) &&
    ((requireKnownDimensions && !upscaleDimensionsKnown) || upscaleTooLarge);

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
        prompt: operation === "upscale" ? "" : prompt.trim(),
        idempotencyKey: crypto.randomUUID(),
        inputAssetIds: readyReferences.map((item) => item.assetId),
        rightsConsentConfirmed: operation === "edit" && rightsConsent,
        rightsConsentVersion:
          operation === "edit"
            ? moderationQuery.data?.photo_rights_consent_version
            : undefined,
        ...templateSelectionFromQuote(freshQuote),
      });
    },
    onSuccess: (generation) => {
      void navigate(`/generations/${generation.id}`);
    },
  });

  const clearReferences = () => {
    setRightsConsent(false);
    setReferences((current) => {
      current.forEach((item) => revokeIfLocal(item.previewUrl));
      return [];
    });
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const selectOperation = (next: Operation) => {
    if (next === operation) return;
    setOperation(next);
    setExplicitSlug(null);
    setStudioMode("simple");
    setParams({});
    setActiveTemplateId(null);
    setRestoredTemplateSlug(null);
    setTemplateInputs({});
    setUploadError(null);
    setRightsConsent(false);
    if (next === "create") clearReferences();
    if (next === "upscale") {
      setPrompt("");
      setReferences((current) => {
        current.slice(1).forEach((item) => revokeIfLocal(item.previewUrl));
        return current.slice(0, 1);
      });
    }
  };

  const uploadFiles = async (files: File[]) => {
    setRightsConsent(false);
    const remainingSlots = Math.max(0, maxReferences - references.length);
    const selectedFiles = files.slice(0, remainingSlots);
    if (selectedFiles.length < files.length) {
      setUploadError(`${tx("create.referencesLimit")}: ${maxReferences}`);
    } else {
      setUploadError(null);
    }

    const validFiles = selectedFiles.filter((file) => {
      if (!allowedMime.includes(file.type)) {
        setUploadError(tx("create.invalidType"));
        return false;
      }
      if (file.size > maxInputBytes) {
        setUploadError(tx("create.tooLarge"));
        return false;
      }
      return true;
    });
    const pending = validFiles.map<ReferenceItem>((file) => ({
      localId: crypto.randomUUID(),
      assetId: null,
      previewUrl: URL.createObjectURL(file),
      status: "uploading",
      width: null,
      height: null,
    }));
    setReferences((current) => [...current, ...pending]);

    await Promise.all(
      pending.map(async (item, index) => {
        try {
          const upload = await api.uploadAsset(validFiles[index]!);
          setReferences((current) =>
            current.map((candidate) =>
              candidate.localId === item.localId
                ? {
                    ...candidate,
                    assetId: upload.asset_id,
                    status: "ready",
                    width: upload.width ?? candidate.width,
                    height: upload.height ?? candidate.height,
                  }
                : candidate,
            ),
          );
        } catch {
          setReferences((current) =>
            current.map((candidate) =>
              candidate.localId === item.localId
                ? { ...candidate, status: "error" }
                : candidate,
            ),
          );
        }
      }),
    );
  };

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length) void uploadFiles(files);
  };

  const removeReference = (localId: string) => {
    setRightsConsent(false);
    setReferences((current) => {
      const removed = current.find((item) => item.localId === localId);
      if (removed) revokeIfLocal(removed.previewUrl);
      return current.filter((item) => item.localId !== localId);
    });
  };

  const captureDimensions = (
    localId: string,
    event: SyntheticEvent<HTMLImageElement>,
  ) => {
    const width = event.currentTarget.naturalWidth || null;
    const height = event.currentTarget.naturalHeight || null;
    if (!width || !height) return;
    setReferences((current) =>
      current.map((item) =>
        item.localId === localId && (!item.width || !item.height)
          ? { ...item, width, height }
          : item,
      ),
    );
  };

  const applyTemplate = (templateId: string) => {
    if (activeTemplateId === templateId) {
      setActiveTemplateId(null);
      setRestoredTemplateSlug(null);
      setTemplateInputs({});
      return;
    }
    const template = imageTemplates.find((item) => item.id === templateId);
    if (!template) return;
    setActiveTemplateId(template.id);
    setRestoredTemplateSlug(template.slug);
    setTemplateInputs({});
    setPrompt(template.prompt_preset.slice(0, maxPromptChars));
    if (aspects.includes(template.aspect_ratio)) {
      setParams((current) => ({ ...current, aspect_ratio: template.aspect_ratio }));
    }
  };

  useEffect(() => {
    if (!recipeParam || recipeHydratedRef.current === recipeParam || !studioModels.length) return;
    const template = imageTemplates.find((item) => item.slug === recipeParam);
    if (!template) return;
    recipeHydratedRef.current = recipeParam;
    setOperation("create");
    setStudioMode("simple");
    setActiveTemplateId(template.id);
    setRestoredTemplateSlug(template.slug);
    setPrompt(template.prompt_preset.slice(0, maxPromptChars));
    if (aspects.includes(template.aspect_ratio)) {
      setParams((current) => ({ ...current, aspect_ratio: template.aspect_ratio }));
    }
  }, [aspects, imageTemplates, maxPromptChars, recipeParam, studioModels.length]);

  const clearContinuation = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("from");
    next.delete("mode");
    next.delete("task");
    setSearchParams(next, { replace: true });
    hydratedKeyRef.current = null;
    setContinuation(null);
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
  if (templatesQuery.isError) {
    return (
      <ErrorState
        title={language === "ru" ? "Не удалось загрузить каталог шаблонов" : "Үлгілер каталогы жүктелмеді"}
        onRetry={() => void templatesQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }
  if (!studioModels.length) return <EmptyState title={tx("create.noModels")} />;

  const submitDisabled =
    !selected ||
    (operation !== "upscale" && !prompt.trim()) ||
    !quote ||
    insufficient ||
    uploadsPending ||
    referencesMissing ||
    referencesOverLimit ||
    upscaleBlocked ||
    createMutation.isPending ||
    !templateValid ||
    (operation === "edit" && (!moderationQuery.data || !rightsConsent));

  const operationOptions: Array<{
    id: Operation;
    glyph: string;
    title: ReturnType<typeof tx>;
    help: ReturnType<typeof tx>;
  }> = [
    {
      id: "create",
      glyph: "+",
      title: tx("create.operationCreate"),
      help: tx("create.operationCreateHelp"),
    },
    {
      id: "edit",
      glyph: "⌁",
      title: tx("create.operationEdit"),
      help: tx("create.operationEditHelp"),
    },
    {
      id: "upscale",
      glyph: "2×",
      title: tx("create.operationUpscale"),
      help: tx("create.operationUpscaleHelp"),
    },
  ];

  return (
    <section className="create-studio studio-operations">
      <header className="studio-header">
        <div>
          <p className="eyebrow">KELBET CREATIVE ATELIER</p>
          <h1>{tx("create.title")}</h1>
          <p className="muted studio-subtitle">{tx("create.subtitle")}</p>
        </div>
        <div className="balance-pill" aria-label={tx("create.balance")}>
          <span className="balance-gem" aria-hidden />
          <strong>{meQuery.data?.available ?? "—"}</strong>
        </div>
      </header>

      {sourceId && draftQuery.isLoading ? (
        <div className="continuation-banner is-loading" role="status">
          <span className="continuation-mark" aria-hidden>↻</span>
          <p>{tx("create.restoring")}</p>
        </div>
      ) : null}
      {sourceId && draftQuery.isError ? (
        <div className="continuation-banner is-warning" role="alert">
          <span className="continuation-mark" aria-hidden>!</span>
          <div>
            <strong>{tx("create.restoreError")}</strong>
            <button type="button" onClick={() => void draftQuery.refetch()}>
              {tx("common.retry")}
            </button>
          </div>
        </div>
      ) : null}
      {continuation ? (
        <div className={`continuation-banner${continuation.missingReferences ? " is-warning" : ""}`}>
          <span className="continuation-mark" aria-hidden>
            {continuation.mode === "upscale" ? "2×" : continuation.mode === "remix" ? "◇" : "↻"}
          </span>
          <div>
            <strong>
              {continuation.mode === "upscale"
                ? tx("create.upscaleRestored")
                : continuation.mode === "remix"
                  ? tx("create.remixRestored")
                  : tx("create.repeatRestored")}
            </strong>
            {continuation.modelChanged ? <p>{tx("create.modelChanged")}</p> : null}
            {continuation.missingReferences ? <p>{tx("create.referenceExpired")}</p> : null}
          </div>
          <button
            type="button"
            className="continuation-clear"
            aria-label={tx("create.clearContinuation")}
            onClick={clearContinuation}
          >
            ×
          </button>
        </div>
      ) : null}

      <section className="operation-console" aria-labelledby="operation-label">
        <div className="console-rule">
          <span id="operation-label">{tx("create.operationLabel")}</span>
          <span>01 — 03</span>
        </div>
        <div className="operation-selector">
          {operationOptions.map((option, index) => (
            <button
              key={option.id}
              type="button"
              className={operation === option.id ? "selected" : ""}
              aria-pressed={operation === option.id}
              onClick={() => selectOperation(option.id)}
            >
              <span className="operation-number">0{index + 1}</span>
              <span className="operation-glyph" aria-hidden>{option.glyph}</span>
              <strong>{option.title}</strong>
              <small>{option.help}</small>
              <span className="operation-light" aria-hidden />
            </button>
          ))}
        </div>
      </section>

      {operation !== "upscale" ? (
        <section className="promise-console" aria-labelledby="promise-label">
          <div className="console-rule">
            <span id="promise-label">{tx("create.promiseLabel")}</span>
            {etaSeconds ? <span>{tx("create.eta")} ~{etaSeconds}s</span> : null}
          </div>
          <div className="promise-selector">
            {(["smart", "fast", "quality"] as PromiseTier[]).map((tier) => (
              <button
                key={tier}
                type="button"
                className={`${promiseTier === tier ? "selected" : ""} tier-${tier}`}
                aria-pressed={promiseTier === tier}
                onClick={() => setPromiseTier(tier)}
              >
                <strong>{tx(`create.${tier}` as "create.smart")}</strong>
                <small>{tx(`create.${tier}Help` as "create.smartHelp")}</small>
              </button>
            ))}
          </div>
          {promiseTier === "smart" ? (
            <p className="smart-resolution" aria-live="polite">
              <span aria-hidden />
              {smartResolvedTier === "quality"
                ? tx("create.smartPickedQuality")
                : tx("create.smartPickedFast")}
              {selected ? ` · ${selected.localization.name}` : ""}
            </p>
          ) : null}
        </section>
      ) : (
        <div className="precision-promise">
          <span className="precision-mark" aria-hidden>2×</span>
          <div>
            <p className="eyebrow">{tx("create.promiseLabel")}</p>
            <strong>{tx("create.upscalePromise")}</strong>
            <small>{selected?.localization.name}</small>
          </div>
          {etaSeconds ? <span>{tx("create.eta")} ~{etaSeconds}s</span> : null}
        </div>
      )}

      {operation !== "upscale" && (imageTemplates.length || templateUnavailable) ? (
        <section className="recipe-section" aria-labelledby="recipe-title">
          <div className="recipe-heading">
            <div>
              <p className="eyebrow">{tx("create.templatesEyebrow")}</p>
              <h2 id="recipe-title">{tx("create.templatesTitle")}</h2>
            </div>
            <span>{String(imageTemplates.length).padStart(2, "0")}</span>
          </div>
          <div className="recipe-shelf">
            {imageTemplates.map((template, index) => (
              <button
                key={template.id}
                type="button"
                className={activeTemplateId === template.id ? "active" : ""}
                aria-pressed={activeTemplateId === template.id}
                onClick={() => applyTemplate(template.id)}
              >
                <span className="recipe-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="recipe-glyph" aria-hidden>{templateMarker(template)}</span>
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
      ) : null}

      <input
        ref={fileInputRef}
        className="visually-hidden"
        type="file"
        accept={allowedMime.join(",")}
        multiple={operation === "edit"}
        onChange={handleFiles}
      />

      {operation !== "create" ? (
        <section className="studio-panel contact-sheet-panel" aria-labelledby="references-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                {operation === "upscale" ? tx("create.upscaleSource") : tx("create.references")}
              </p>
              <h2 id="references-title">
                {operation === "upscale"
                  ? tx("create.upscaleSourceHelp")
                  : tx("create.referencesHelp")}
              </h2>
            </div>
            <span className="reference-meter">{references.length}/{maxReferences}</span>
          </div>

          {references.length ? (
            <div className={`contact-sheet${operation === "upscale" ? " is-single" : ""}`}>
              {references.map((item, index) => (
                <article key={item.localId} className={`contact-frame state-${item.status}`}>
                  <div className="contact-image">
                    <img
                      src={item.previewUrl}
                      alt={`${tx("create.figure")} ${index + 1}`}
                      onLoad={(event) => captureDimensions(item.localId, event)}
                    />
                    {item.status === "uploading" ? <span className="contact-scan" /> : null}
                  </div>
                  <footer>
                    <div>
                      <strong>
                        {tx("create.figure")} {String(index + 1).padStart(2, "0")}
                      </strong>
                      <small>
                        {item.status === "uploading"
                          ? tx("create.uploading")
                          : item.status === "error"
                            ? tx("create.uploadError")
                            : `${item.width ?? "?"}×${item.height ?? "?"}`}
                      </small>
                    </div>
                    <button
                      type="button"
                      aria-label={`${tx("create.removeReference")} ${index + 1}`}
                      onClick={() => removeReference(item.localId)}
                    >
                      ×
                    </button>
                  </footer>
                </article>
              ))}
              {references.length < maxReferences ? (
                <button
                  type="button"
                  className="contact-add"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <span aria-hidden>+</span>
                  {tx("create.addReferences")}
                </button>
              ) : null}
            </div>
          ) : (
            <button
              type="button"
              className="upload-zone atelier-upload"
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="upload-icon" aria-hidden>＋</span>
              <strong>
                {operation === "upscale" ? tx("create.choosePhoto") : tx("create.addReferences")}
              </strong>
              <span>
                {operation === "upscale"
                  ? tx("create.upscaleEligibility")
                  : `${tx("create.referencesLimit")}: ${maxReferences}`}
              </span>
            </button>
          )}
          {operation === "edit" ? <p className="figure-instruction">{tx("create.referencesHelp")}</p> : null}
          {operation === "upscale" && upscaleSource && !upscaleDimensionsKnown ? (
            <p className="field-error">{tx("create.upscaleUnverified")}</p>
          ) : null}
          {upscaleTooLarge ? <p className="field-error">{tx("create.upscaleTooLarge")}</p> : null}
          {uploadError ? <p className="field-error">{uploadError}</p> : null}
        </section>
      ) : null}

      {operation !== "upscale" ? (
        <section className="studio-panel prompt-section" aria-labelledby="prompt-label">
          <div className="section-heading">
            <h2 id="prompt-label">{tx("create.prompt")}</h2>
            <span className="character-count">{prompt.length}/{maxPromptChars}</span>
          </div>
          <label className="visually-hidden" htmlFor="image-prompt">{tx("create.prompt")}</label>
          <textarea
            id="image-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={tx("create.promptHint")}
            maxLength={maxPromptChars}
          />
          <p className="suggestion-label">{tx("create.promptExample")}</p>
          <div className="suggestion-row">
            {[
              tx("create.suggestionLight"),
              tx("create.suggestionDetail"),
              tx("create.suggestionComposition"),
              tx("create.suggestionTexture"),
            ].map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() =>
                  setPrompt((current) =>
                    `${current.trimEnd()}${current.trim() ? ", " : ""}${suggestion}`.slice(
                      0,
                      maxPromptChars,
                    ),
                  )
                }
              >
                + {suggestion}
              </button>
            ))}
          </div>
          <PromptAssistant prompt={prompt} setPrompt={setPrompt} modelMaxChars={maxPromptChars} />
        </section>
      ) : null}

      {operation === "upscale" && flavors.length ? (
        <section className="studio-panel upscale-flavor-panel" aria-labelledby="flavor-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{tx("create.upscalePromise")}</p>
              <h2 id="flavor-title">{tx("create.flavor")}</h2>
            </div>
          </div>
          <div className="flavor-grid">
            {flavors.map((flavor, index) => {
              const labels = [
                tx("create.flavorPhoto"),
                tx("create.flavorDenoiser"),
                tx("create.flavorSublime"),
              ];
              return (
                <button
                  key={flavor}
                  type="button"
                  className={params.flavor === flavor ? "selected" : ""}
                  onClick={() => setParams((current) => ({ ...current, flavor }))}
                >
                  <span>0{index + 1}</span>
                  {labels[index] ?? flavor}
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <details
        className="studio-panel pro-disclosure"
        open={studioMode === "advanced"}
        onToggle={(event) => {
          const open = event.currentTarget.open;
          setStudioMode(open ? "advanced" : "simple");
          if (!open) setExplicitSlug(null);
        }}
      >
        <summary>
          <span className="pro-toggle-light" aria-hidden />
          <span>
            <strong>{tx("create.proControls")}</strong>
            <small>{tx("create.proControlsHelp")}</small>
          </span>
          <span className="pro-state">{studioMode === "advanced" ? "ON" : "OFF"}</span>
        </summary>

        {operationModels.length > 1 ? (
          <fieldset className="setting-group model-picker">
            <legend>{tx("create.model")}</legend>
            <div className="model-list">
              {operationModels.map((model) => (
                <button
                  key={model.slug}
                  type="button"
                  className={selected?.slug === model.slug ? "selected" : ""}
                  onClick={() => {
                    setExplicitSlug(model.slug);
                    setParams((current) => compatibleParams(model, operation, current));
                  }}
                >
                  <span>
                    <strong>{model.localization.name}</strong>
                    <small>{model.localization.description}</small>
                  </span>
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {operation !== "upscale" && aspects.length ? (
          <fieldset className="setting-group">
            <legend>{tx("create.aspect")}</legend>
            <div className="option-grid aspect-grid">
              {aspects.map((aspect) => (
                <button
                  key={aspect}
                  type="button"
                  className={params.aspect_ratio === aspect ? "selected" : ""}
                  onClick={() => setParams((current) => ({ ...current, aspect_ratio: aspect }))}
                >
                  {aspect}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {operation !== "upscale" && resolutions.length ? (
          <fieldset className="setting-group">
            <legend>{tx("create.resolution")}</legend>
            <div className="option-grid resolution-grid">
              {resolutions.map((resolution) => (
                <button
                  key={resolution}
                  type="button"
                  className={params.resolution === resolution ? "selected" : ""}
                  onClick={() => setParams((current) => ({ ...current, resolution }))}
                >
                  {resolution}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {operation === "upscale" ? (
          <>
            {([
              { key: "sharpen", label: tx("create.sharpen") },
              { key: "smart_grain", label: tx("create.smartGrain") },
              { key: "ultra_detail", label: tx("create.ultraDetail") },
            ] as const).map((control) => (
              <label className="precision-slider" key={control.key}>
                <span>
                  {control.label}
                  <strong>{numericCapability(params[control.key], 0)}</strong>
                </span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={numericCapability(params[control.key], 0)}
                  onChange={(event) =>
                    setParams((current) => ({
                      ...current,
                      [control.key]: Number(event.target.value),
                    }))
                  }
                />
              </label>
            ))}
          </>
        ) : null}
      </details>

      {operation === "edit" ? (
        <PhotoRightsConsent
          id="create-photo-rights"
          language={language}
          config={moderationQuery.data}
          checked={rightsConsent}
          loading={moderationQuery.isLoading}
          error={moderationQuery.isError}
          onChange={setRightsConsent}
        />
      ) : null}

      <div className="create-action-spacer" />
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
          disabled={submitDisabled}
          onClick={() => createMutation.mutate()}
        >
          {createMutation.isPending
            ? tx("create.creating")
            : insufficient
              ? tx("create.insufficient")
              : quote
                ? `${tx("create.submitWithPrice")} ${quote.user_credit_price}`
                : tx("create.submit")}
          {!createMutation.isPending && !insufficient ? <span aria-hidden>→</span> : null}
        </button>
        {referencesMissing && !uploadsPending && operation !== "create" ? (
          <p className="action-hint">{tx("create.missingReference")}</p>
        ) : null}
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
    </section>
  );
}
