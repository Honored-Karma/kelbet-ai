import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../shared/api/client";
import type { AssetDownload, HistoryItem } from "../shared/api/types";
import { isActiveGeneration } from "../shared/generation/status";
import { useI18n } from "../shared/i18n/runtime";
import type { MessageKey } from "../shared/i18n/messages";
import { EmptyState } from "../shared/ui/EmptyState";
import { ErrorState } from "../shared/ui/ErrorState";

type HistoryFilter = "all" | "image" | "video" | "active";

const filterLabels: Record<HistoryFilter, MessageKey> = {
  all: "history.filterAll",
  image: "history.filterImage",
  video: "history.filterVideo",
  active: "history.filterActive",
};

function statusMeta(status: string): { label: MessageKey; tone: string } {
  if (status === "succeeded") return { label: "history.ready", tone: "ready" };
  if (isActiveGeneration(status)) return { label: "history.active", tone: "active" };
  if (status === "cancelled") return { label: "history.cancelled", tone: "cancelled" };
  return { label: "history.failed", tone: "failed" };
}

function workLabel(item: HistoryItem): "history.imageWork" | "history.videoWork" {
  return item.modality === "video" ? "history.videoWork" : "history.imageWork";
}

function HistoryArtwork({
  item,
  preview,
}: {
  item: HistoryItem;
  preview?: AssetDownload;
}) {
  const { tx } = useI18n();
  const status = statusMeta(item.status);
  const isImage =
    item.preview_content_type?.startsWith("image/") &&
    preview?.content_type.startsWith("image/");

  if (isImage && preview) {
    return (
      <img
        src={preview.download_url}
        alt={tx("history.previewAlt")}
        loading="lazy"
        decoding="async"
      />
    );
  }

  if (isActiveGeneration(item.status)) {
    return (
      <div className="history-artwork-state is-active">
        <span className="history-working-mark" aria-hidden>
          <i />
          <b>{item.progress_pct}%</b>
        </span>
        <strong>{tx(status.label)}</strong>
        <span className="history-mini-progress">
          <i style={{ width: `${Math.max(4, item.progress_pct)}%` }} />
        </span>
      </div>
    );
  }

  if (item.modality === "video") {
    return (
      <div className="history-artwork-state is-video">
        <span aria-hidden>▶</span>
        <strong>{tx("history.videoPreview")}</strong>
      </div>
    );
  }

  return (
    <div className={`history-artwork-state is-${status.tone}`}>
      <span className="history-state-glyph" aria-hidden>{status.tone === "failed" ? "×" : "◇"}</span>
      <strong>{status.tone === "failed" ? tx("history.failed") : tx("history.noPreview")}</strong>
    </div>
  );
}

export function HistoryPage() {
  const { tx, language } = useI18n();
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: () => api.history(),
  });
  const previewIds = useMemo(
    () =>
      Array.from(
        new Set(
          (historyQuery.data ?? [])
            .map((item) => item.preview_asset_id)
            .filter((id): id is string => Boolean(id)),
        ),
      ).slice(0, 20),
    [historyQuery.data],
  );
  const previewsQuery = useQuery({
    queryKey: ["history-previews", previewIds.join(",")],
    queryFn: () => api.getAssets(previewIds),
    enabled: previewIds.length > 0,
    staleTime: 8 * 60_000,
    retry: 1,
  });
  const previewById = useMemo(
    () => new Map((previewsQuery.data ?? []).map((asset) => [asset.id, asset])),
    [previewsQuery.data],
  );
  const filteredHistory = useMemo(
    () =>
      (historyQuery.data ?? []).filter((item) => {
        if (filter === "all") return true;
        if (filter === "active") return isActiveGeneration(item.status);
        if (filter === "video") return item.modality === "video";
        return item.modality !== "video";
      }),
    [filter, historyQuery.data],
  );

  if (historyQuery.isLoading) {
    return (
      <section className="history-page">
        <div className="history-heading-skeleton skeleton" />
        <div className="history-gallery" aria-label={tx("common.loading")}>
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="history-card-skeleton skeleton" />
          ))}
        </div>
      </section>
    );
  }
  if (historyQuery.isError) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void historyQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }
  if (!historyQuery.data?.length) {
    return (
      <EmptyState
        title={tx("history.empty")}
        action={
          <Link to="/create" className="btn">
            {tx("home.cta")}
          </Link>
        }
      />
    );
  }

  return (
    <section className="history-page rise">
      <header className="history-header">
        <div>
          <p className="eyebrow">{tx("history.eyebrow")}</p>
          <h1>{tx("history.title")}</h1>
        </div>
        <span className="archive-count">{String(historyQuery.data.length).padStart(2, "0")}</span>
        <p>{tx("history.subtitle")}</p>
      </header>

      <div className="history-filters" role="group" aria-label={tx("history.filterLabel")}>
        {(["all", "image", "video", "active"] as HistoryFilter[]).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={filter === item}
            className={filter === item ? "active" : ""}
            onClick={() => setFilter(item)}
          >
            {tx(filterLabels[item])}
          </button>
        ))}
      </div>

      {filteredHistory.length ? (
        <div className="history-gallery">
        {filteredHistory.map((item, index) => {
          const status = statusMeta(item.status);
          const preview = item.preview_asset_id
            ? previewById.get(item.preview_asset_id)
            : undefined;
          return (
            <Link
              key={item.id}
              to={`/generations/${item.id}`}
              className={`history-card history-card-${index % 3}`}
              aria-label={`${tx("history.itemOpen")}: ${tx(workLabel(item))}`}
            >
              <div className="history-artwork">
                <HistoryArtwork item={item} preview={preview} />
                <span className={`history-status is-${status.tone}`}>
                  <i aria-hidden />
                  {tx(status.label)}
                </span>
                <span className="history-index" aria-hidden>
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <div className="history-meta">
                <strong>{tx(workLabel(item))}</strong>
                <span>
                  {new Intl.DateTimeFormat(language === "kk" ? "kk-KZ" : "ru-KZ", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  }).format(new Date(item.created_at))}
                </span>
                <b>{item.user_credit_price} {tx("history.credits")}</b>
              </div>
            </Link>
          );
        })}
        </div>
      ) : (
        <div className="history-filter-empty">
          <strong>{tx("history.filterEmpty")}</strong>
          <button type="button" onClick={() => setFilter("all")}>
            {tx("history.filterAll")}
          </button>
        </div>
      )}
    </section>
  );
}
