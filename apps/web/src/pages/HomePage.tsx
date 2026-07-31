import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import contactSheet from "../assets/kelbet-contact-sheet.webp";
import { CREATE_TEMPLATES } from "../features/create/templates";
import { TREND_TEMPLATES } from "../features/trends/templates";
import { api } from "../shared/api/client";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

export function HomePage() {
  const { tx, language } = useI18n();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: () => api.history(),
    retry: 1,
  });
  const recent = useMemo(() => historyQuery.data?.slice(0, 3) ?? [], [historyQuery.data]);
  const previewIds = useMemo(
    () =>
      recent
        .map((item) => item.preview_asset_id)
        .filter((id): id is string => Boolean(id)),
    [recent],
  );
  const previewsQuery = useQuery({
    queryKey: ["home-previews", previewIds.join(",")],
    queryFn: () => api.getAssets(previewIds),
    enabled: previewIds.length > 0,
    retry: 1,
    staleTime: 8 * 60_000,
  });
  const previewById = useMemo(
    () => new Map((previewsQuery.data ?? []).map((asset) => [asset.id, asset])),
    [previewsQuery.data],
  );

  if (meQuery.isLoading) {
    return <SkeletonBlock rows={5} />;
  }
  if (meQuery.isError || !meQuery.data) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void meQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }

  const me = meQuery.data;
  return (
    <section className="home-page rise">
      <header className="home-masthead">
        <div className="home-brand-line">
          <Link to="/" className="home-wordmark" aria-label="KELBET AI">
            <span aria-hidden>K</span>
            <strong>KELBET</strong>
          </Link>
          <Link to="/plans" className="home-balance" aria-label={tx("home.available")}>
            <span>{tx("home.available")}</span>
            <strong><i aria-hidden>◆</i>{me.available}</strong>
          </Link>
        </div>
        <p className="eyebrow">{tx("home.eyebrow")}</p>
        <h1>
          {tx("home.titleLead")}
          <span>{tx("home.titleAccent")}</span>
        </h1>
        <p className="home-tagline">{tx("home.tagline")}</p>
      </header>

      <figure className="home-contact-sheet">
        <img src={contactSheet} alt={tx("home.contactAlt")} />
        <span className="contact-corner top-left" aria-hidden />
        <span className="contact-corner bottom-right" aria-hidden />
        <figcaption>
          <span>KELBET / SELECTED WORK 01—04</span>
          <strong>{tx("home.contactCaption")}</strong>
        </figcaption>
        <div className="contact-live" aria-hidden><span /> LIVE STUDIO</div>
      </figure>

      <div className="home-task-grid" aria-label={tx("home.chooseStudio")}>
        <Link to="/create" className="home-task-card image-task">
          <span className="home-task-index">01 / STILL</span>
          <span className="home-task-glyph"><Icon name="image" /></span>
          <span>
            <strong>{tx("home.imageStudio")}</strong>
            <small>{tx("home.imageStudioHelp")}</small>
          </span>
          <span className="home-task-arrow"><Icon name="arrow" /></span>
        </Link>
        <Link to="/video" className="home-task-card video-task">
          <span className="home-task-index">02 / MOTION</span>
          <span className="home-task-glyph"><Icon name="video" /></span>
          <span>
            <strong>{tx("home.videoStudio")}</strong>
            <small>{tx("home.videoStudioHelp")}</small>
          </span>
          <span className="home-task-arrow"><Icon name="arrow" /></span>
        </Link>
      </div>

      <section className="home-trends" aria-labelledby="home-trends-title">
        <header className="home-section-heading">
          <div>
            <p className="eyebrow">{tx("home.trendsEyebrow")}</p>
            <h2 id="home-trends-title">{tx("home.trendsTitle")}</h2>
          </div>
          <Link to="/trends">
            {tx("home.trendsAll")} <Icon name="arrow" />
          </Link>
        </header>
        <div className="home-trend-rail">
          {TREND_TEMPLATES.slice(0, 4).map((trend) => (
            <Link
              key={trend.id}
              to={`/trends?trend=${encodeURIComponent(trend.id)}`}
              className="home-trend-card"
            >
              <span className="home-trend-visual" aria-hidden>
                <img src={trend.preview} alt="" loading="lazy" decoding="async" />
                <i>{trend.kind === "video" ? "MOTION" : "STILL"}</i>
              </span>
              <strong>{trend.title[language]}</strong>
              <small>{trend.description[language]}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="home-recipes" aria-labelledby="home-recipes-title">
        <header className="home-section-heading">
          <div>
            <p className="eyebrow">{tx("home.recipesEyebrow")}</p>
            <h2 id="home-recipes-title">{tx("home.recipesTitle")}</h2>
          </div>
          <span>03 / 06</span>
        </header>
        <div className="home-recipe-rail">
          {CREATE_TEMPLATES.slice(0, 3).map((template, index) => (
            <Link
              key={template.id}
              to={`/create?recipe=${encodeURIComponent(template.id)}`}
              className={`home-recipe recipe-${index + 1}`}
            >
              <span className="home-recipe-visual" aria-hidden>
                <i>{String(index + 1).padStart(2, "0")}</i>
              </span>
              <strong>{template.title[language]}</strong>
              <small>{template.description[language]}</small>
              <b>{template.aspectRatio}</b>
            </Link>
          ))}
        </div>
      </section>

      <section className="home-archive" aria-labelledby="home-archive-title">
        <header className="home-section-heading">
          <div>
            <p className="eyebrow">{tx("home.archiveEyebrow")}</p>
            <h2 id="home-archive-title">{tx("home.archiveTitle")}</h2>
          </div>
          <Link to="/history">
            {tx("home.viewAll")} <Icon name="arrow" />
          </Link>
        </header>
        {recent.length ? (
          <div className="home-recent-list">
            {recent.map((item, index) => {
              const preview = item.preview_asset_id
                ? previewById.get(item.preview_asset_id)
                : undefined;
              return (
                <Link key={item.id} to={`/generations/${item.id}`} className="home-recent-item">
                  <span className="home-recent-preview">
                    {preview?.content_type.startsWith("image/") ? (
                      <img src={preview.download_url} alt="" loading="lazy" decoding="async" />
                    ) : (
                      <Icon name={item.modality === "video" ? "video" : "image"} />
                    )}
                  </span>
                  <span>
                    <strong>{item.modality === "video" ? "MOTION" : "STILL"} / {String(index + 1).padStart(2, "0")}</strong>
                    <small>{item.user_credit_price} cr · {item.status}</small>
                  </span>
                  <Icon name="arrow" />
                </Link>
              );
            })}
          </div>
        ) : (
          <Link to="/history" className="home-archive-empty">
            <span><Icon name="history" /></span>
            <div>
              <strong>{tx("home.archiveEmpty")}</strong>
              <small>{tx("home.archiveHelp")}</small>
            </div>
            <Icon name="arrow" />
          </Link>
        )}
      </section>
    </section>
  );
}
