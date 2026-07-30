import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../shared/api/client";
import { ApiError } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

const ACTIVE = new Set(["queued", "created", "submitting", "running", "finalizing"]);
const TERMINAL = new Set(["succeeded", "failed", "timed_out", "cancelled"]);

function extensionFor(contentType: string): string {
  if (contentType === "image/jpeg") return "jpg";
  if (contentType === "image/webp") return "webp";
  if (contentType === "image/gif") return "gif";
  if (contentType === "video/mp4") return "mp4";
  if (contentType === "video/webm") return "webm";
  return "png";
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function isUnavailableError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 404 || ["generation_not_found", "not_found"].includes(error.code);
  }
  return error instanceof Error && error.message === "not_found";
}

export function GenerationPage() {
  const { id = "" } = useParams();
  const { tx, language } = useI18n();
  const queryClient = useQueryClient();
  const invalidatedStatusRef = useRef<string | null>(null);

  const generationQuery = useQuery({
    queryKey: ["generation", id],
    queryFn: () => api.getGeneration(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ACTIVE.has(status) ? 1200 : false;
    },
  });

  const generation = generationQuery.data;
  const isVideo = generation?.modality === "video";
  const modelsQuery = useQuery({
    queryKey: ["catalog", language],
    queryFn: () => api.listModels(language),
    enabled: Boolean(isVideo),
    staleTime: 5 * 60_000,
  });
  const generationModel = modelsQuery.data?.find(
    (model) => model.slug === generation?.model_slug,
  );
  const sourceImageRequirement = generationModel?.input_requirements.source_image;
  const canAnimatePhoto =
    isVideo &&
    (sourceImageRequirement === "optional" || sourceImageRequirement === "required") &&
    Number(generationModel?.input_requirements.max_input_assets ?? 0) >= 1;
  const outputAssetId = generation?.output_asset_ids[0] ?? "";
  const done = generation?.status === "succeeded";
  const assetQuery = useQuery({
    queryKey: ["asset", outputAssetId],
    queryFn: () => api.getAsset(outputAssetId),
    enabled: Boolean(done && outputAssetId),
    staleTime: 8 * 60_000,
    retry: 1,
  });

  useEffect(() => {
    const status = generation?.status;
    if (!status || !TERMINAL.has(status) || invalidatedStatusRef.current === status) return;
    invalidatedStatusRef.current = status;
    void queryClient.invalidateQueries({ queryKey: ["me"] });
    void queryClient.invalidateQueries({ queryKey: ["history"] });
  }, [generation?.status, queryClient]);

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelGeneration(id),
    onSuccess: (data) => {
      queryClient.setQueryData(["generation", id], data);
    },
  });

  const shareMutation = useMutation({
    mutationFn: async () => {
      const asset = assetQuery.data;
      if (!asset || !navigator.share) throw new Error("unsupported");
      const response = await fetch(asset.download_url);
      if (!response.ok) throw new Error("download_failed");
      const blob = await response.blob();
      const extension = extensionFor(asset.content_type);
      const file = new File([blob], `kelbet-${generation?.id}.${extension}`, {
        type: asset.content_type,
      });
      const shareData: ShareData = { files: [file], title: "KELBET Studio" };
      if (navigator.canShare && !navigator.canShare(shareData)) {
        throw new Error("unsupported");
      }
      await navigator.share(shareData);
    },
  });

  if (generationQuery.isLoading) return <SkeletonBlock rows={5} />;
  if (generationQuery.isError && isUnavailableError(generationQuery.error)) {
    return (
      <section className="generation-unavailable rise" aria-labelledby="unavailable-title">
        <div className="unavailable-frame" aria-hidden>
          <span>404</span>
          <i>K</i>
        </div>
        <div className="unavailable-copy">
          <p className="eyebrow">KELBET / ARCHIVE</p>
          <h1 id="unavailable-title">{tx("generation.unavailableTitle")}</h1>
          <p>{tx("generation.unavailableBody")}</p>
        </div>
        <div className="unavailable-actions">
          <Link className="btn unavailable-history" to="/history">
            <Icon name="history" />
            {tx("generation.backToHistory")}
          </Link>
          <Link className="btn btn-ghost" to="/create">
            <Icon name="image" />
            {tx("generation.createImage")}
          </Link>
          <Link className="btn btn-ghost" to="/video">
            <Icon name="video" />
            {tx("generation.createVideo")}
          </Link>
        </div>
      </section>
    );
  }
  if (generationQuery.isError || !generation) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void generationQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }

  const active = ACTIVE.has(generation.status);
  const cancelled = generation.status === "cancelled";
  const failed = ["failed", "timed_out"].includes(generation.status);
  const progress = Math.min(100, Math.max(4, generation.progress_pct));
  const ui = recordValue(generationModel?.capabilities.ui);
  const catalogEta =
    typeof ui.eta_seconds === "number" && Number.isFinite(ui.eta_seconds) ? ui.eta_seconds : 0;
  const totalEta = generation.eta_seconds ?? catalogEta;
  const remainingEta =
    generation.estimated_remaining_seconds ??
    (totalEta
      ? Math.max(15, Math.ceil((totalEta * (100 - generation.progress_pct)) / 100 / 15) * 15)
      : 0);
  const stageKey =
    generation.progress_stage === "queued" || generation.status === "queued"
      ? "generation.stageQueued"
      : generation.progress_stage === "submitting" || generation.status === "submitting"
        ? "generation.stageSubmitting"
        : generation.progress_stage === "finalizing" || generation.status === "finalizing"
          ? "generation.stageFinalizing"
          : "generation.stageRunning";
  const routeLabel =
    generation.modality === "video"
      ? tx("generation.routeVideo")
      : generation.modality === "upscale"
        ? tx("generation.routeUpscale")
        : tx("generation.routeImage");

  return (
    <section className="result-page rise">
      <header className="result-header">
        <p className="eyebrow">{isVideo ? "KELBET MOTION ATELIER" : "KELBET STUDIO"}</p>
        <h1>{tx(isVideo ? "generation.videoTitle" : "generation.title")}</h1>
      </header>

      <div
        className={`result-canvas${isVideo ? " is-video" : ""}${active ? " is-active" : ""}${failed || cancelled ? " is-failed" : ""}`}
      >
        {done && assetQuery.data ? (
          isVideo || assetQuery.data.content_type.startsWith("video/") ? (
            <video
              src={assetQuery.data.download_url}
              aria-label={tx("generation.videoResultAlt")}
              controls
              playsInline
              preload="metadata"
            />
          ) : (
            <img src={assetQuery.data.download_url} alt={tx("generation.resultAlt")} />
          )
        ) : done && assetQuery.isError ? (
          <div className="result-message">
            <span className="result-symbol" aria-hidden>
              ↻
            </span>
            <h2>{tx("common.error")}</h2>
            <button type="button" className="btn btn-ghost" onClick={() => void assetQuery.refetch()}>
              {tx("generation.refresh")}
            </button>
          </div>
        ) : done ? (
          <div className="result-skeleton" aria-label={tx("common.loading")}>
            <span />
          </div>
        ) : active ? (
          <div className="creative-loader" aria-hidden>
            <span className="loader-frame frame-one" />
            <span className="loader-frame frame-two" />
            <span className="loader-core">K</span>
          </div>
        ) : (
          <div className="result-message">
            <span className="result-symbol" aria-hidden>
              {cancelled ? "×" : "!"}
            </span>
          </div>
        )}
        {active ? (
          <div className="canvas-progress">
            <span style={{ width: `${progress}%` }} />
          </div>
        ) : null}
      </div>

      <div className="result-copy">
        <span className={`status-dot${done ? " ready" : ""}${failed || cancelled ? " stopped" : ""}`} />
        <div>
          <h2>
            {active
              ? tx(isVideo ? "generation.videoActiveTitle" : "generation.activeTitle")
              : done
                ? tx(isVideo ? "generation.videoDone" : "generation.done")
                : cancelled
                  ? tx("generation.cancelled")
                  : tx("generation.failed")}
          </h2>
          <p>
            {active
              ? tx(isVideo ? "generation.videoActiveBody" : "generation.activeBody")
              : done
                ? tx(isVideo ? "generation.videoDoneBody" : "generation.doneBody")
                : cancelled
                  ? tx("generation.cancelledBody")
                  : tx("generation.failedBody")}
          </p>
        </div>
      </div>

      {active ? (
        <div
          className={`generation-progress${isVideo ? " video-generation-progress" : ""}`}
          aria-label={`${generation.progress_pct}%`}
        >
          <div>
            <span>{isVideo ? tx(stageKey) : `${generation.progress_pct}%`}</span>
            <span>
              {isVideo && remainingEta
                ? `${tx("generation.etaRemaining")} ${Math.ceil(remainingEta / 60)} min`
                : `${generation.user_credit_price} cr`}
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${generation.progress_pct}%` }} />
          </div>
          {isVideo ? (
            <div className="result-film-rail" aria-hidden>
              {[18, 42, 68, 92].map((threshold, index) => (
                <span
                  key={threshold}
                  className={generation.progress_pct >= threshold ? "is-ready" : ""}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {done && assetQuery.data ? (
        <div className="result-actions">
          <a
            className="btn result-download"
            href={assetQuery.data.download_url}
            download={`kelbet-${generation.id}.${extensionFor(assetQuery.data.content_type)}`}
          >
            <Icon name="download" />
            {tx("generation.download")}
          </a>
          {isVideo ? (
            <Link
              className="btn result-remix"
              to={`/video?from=${encodeURIComponent(generation.id)}`}
            >
              <Icon name="repeat" />
              {tx("generation.repeat")}
            </Link>
          ) : (
            <Link
              className="btn result-remix"
              to={`/create?from=${encodeURIComponent(generation.id)}&mode=remix`}
            >
              <Icon name="repeat" />
              {tx("generation.remix")}
            </Link>
          )}
          {!isVideo &&
          (generation.modality === "image" || generation.modality === "image_edit") ? (
            <Link
              className="btn result-upscale"
              to={`/create?from=${encodeURIComponent(generation.id)}&mode=upscale&task=upscale`}
            >
              <Icon name="upscale" />
              {tx("generation.upscale")}
            </Link>
          ) : null}
          {canAnimatePhoto ? (
            <Link className="btn result-video-frame" to="/video?mode=photo">
              <Icon name="video" />
              {tx("generation.newPhotoVideo")}
            </Link>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost result-share"
            disabled={shareMutation.isPending}
            onClick={() => shareMutation.mutate()}
          >
            <Icon name="share" />
            {shareMutation.isPending ? tx("generation.sharing") : tx("generation.share")}
          </button>
          {!isVideo ? (
            <Link
              className="btn btn-ghost result-repeat"
              to={`/create?from=${encodeURIComponent(generation.id)}&mode=repeat`}
            >
              <Icon name="repeat" />
              {tx("generation.repeat")}
            </Link>
          ) : null}
          {shareMutation.isError ? (
            <p className="share-note" role="status">
              {shareMutation.error instanceof Error &&
              shareMutation.error.message === "unsupported"
                ? tx("generation.shareUnsupported")
                : tx("generation.shareFailed")}
            </p>
          ) : null}
        </div>
      ) : null}

      {generation.cancelable ? (
        <button
          type="button"
          className="cancel-generation"
          disabled={cancelMutation.isPending}
          onClick={() => cancelMutation.mutate()}
        >
          {tx("generation.cancel")}
        </button>
      ) : null}

      {(failed || cancelled) && !generation.cancelable ? (
        <Link className="btn btn-block" to={isVideo ? "/video" : "/create"}>
          {tx("generation.newWork")}
        </Link>
      ) : null}

      <details className="result-details">
        <summary>{tx("generation.details")}</summary>
        <dl>
          <div>
            <dt>{tx("generation.model")}</dt>
            <dd>{routeLabel}</dd>
          </div>
          <div>
            <dt>{tx("generation.price")}</dt>
            <dd>{generation.user_credit_price} cr</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
