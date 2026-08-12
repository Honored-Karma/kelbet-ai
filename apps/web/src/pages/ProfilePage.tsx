import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../shared/api/client";
import type { AssetDownload, HistoryItem, Language, Me } from "../shared/api/types";
import { isActiveGeneration } from "../shared/generation/status";
import { profileText } from "../shared/i18n/profileCopy";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

const ACTIVITY_WINDOW_DAYS = 30;
const RECENT_WORK_COUNT = 4;

function localeOf(language: Language): string {
  return language === "kk" ? "kk-KZ" : "ru-KZ";
}

function RecentWork({
  item,
  preview,
  language,
}: {
  item: HistoryItem;
  preview?: AssetDownload;
  language: Language;
}) {
  const showsImage =
    item.preview_content_type?.startsWith("image/") &&
    preview?.content_type.startsWith("image/");
  const day = new Intl.DateTimeFormat(localeOf(language), {
    day: "numeric",
    month: "short",
  }).format(new Date(item.created_at));

  return (
    <Link to={`/generations/${item.id}`} className="pf-work" aria-label={day}>
      {showsImage && preview ? (
        <img src={preview.download_url} alt="" loading="lazy" decoding="async" />
      ) : (
        <span className="pf-work-fallback" aria-hidden>
          <Icon name={item.modality === "video" ? "video" : "image"} />
        </span>
      )}
      {item.modality === "video" ? (
        <b className="pf-work-tag" aria-hidden>
          <Icon name="video" />
        </b>
      ) : null}
    </Link>
  );
}

export function ProfilePage() {
  const { tx, language, setLanguage } = useI18n();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const productsQuery = useQuery({
    queryKey: ["payment-products"],
    queryFn: () => api.listPaymentProducts(),
    retry: 1,
  });
  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: () => api.history(),
    retry: 1,
  });
  const referralQuery = useQuery({
    queryKey: ["referrals"],
    queryFn: () => api.getReferralSummary(),
    retry: 1,
  });

  const history = useMemo(() => historyQuery.data ?? [], [historyQuery.data]);
  const activeCount = useMemo(
    () => history.filter((item) => isActiveGeneration(item.status)).length,
    [history],
  );
  const activity = useMemo(() => {
    const cutoff = Date.now() - ACTIVITY_WINDOW_DAYS * 24 * 60 * 60 * 1000;
    const recent = history.filter(
      (item) => new Date(item.created_at).getTime() >= cutoff,
    );
    return {
      images: recent.filter((item) => item.modality !== "video").length,
      videos: recent.filter((item) => item.modality === "video").length,
      credits: recent.reduce((sum, item) => sum + item.user_credit_price, 0),
    };
  }, [history]);
  const recentWorks = useMemo(
    () => history.slice(0, RECENT_WORK_COUNT),
    [history],
  );
  const previewIds = useMemo(
    () =>
      Array.from(
        new Set(
          recentWorks
            .map((item) => item.preview_asset_id)
            .filter((id): id is string => Boolean(id)),
        ),
      ),
    [recentWorks],
  );
  const previewsQuery = useQuery({
    queryKey: ["profile-previews", previewIds.join(",")],
    queryFn: () => api.getAssets(previewIds),
    enabled: previewIds.length > 0,
    staleTime: 8 * 60_000,
    retry: 1,
  });
  const previewById = useMemo(
    () => new Map((previewsQuery.data ?? []).map((asset) => [asset.id, asset])),
    [previewsQuery.data],
  );

  const languageMutation = useMutation({
    mutationFn: (next: Language) => api.patchMe({ language: next }),
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey: ["me"] });
      const previous = queryClient.getQueryData<Me>(["me"]);
      queryClient.setQueryData<Me>(["me"], (current) =>
        current ? { ...current, language: next } : current,
      );
      return { previous };
    },
    onError: (_error, _next, context) => {
      if (!context?.previous) return;
      queryClient.setQueryData(["me"], context.previous);
      setLanguage(context.previous.language);
    },
    onSuccess: (me) => {
      setLanguage(me.language);
      queryClient.setQueryData(["me"], me);
      void queryClient.invalidateQueries({ queryKey: ["catalog"] });
    },
  });
  const notificationMutation = useMutation({
    mutationFn: (enabled: boolean) => api.patchMe({ notify_generation_ready: enabled }),
    onMutate: async (enabled) => {
      await queryClient.cancelQueries({ queryKey: ["me"] });
      const previous = queryClient.getQueryData<Me>(["me"]);
      queryClient.setQueryData<Me>(["me"], (current) =>
        current ? { ...current, notify_generation_ready: enabled } : current,
      );
      return { previous };
    },
    onError: (_error, _enabled, context) => {
      if (context?.previous) queryClient.setQueryData(["me"], context.previous);
    },
    onSuccess: (next) => {
      queryClient.setQueryData(["me"], next);
    },
  });

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
  const identity = me.username?.slice(0, 1).toUpperCase() ?? "K";
  const plan = me.plan === "free" ? "FREE STUDIO" : me.plan.toUpperCase();
  const referral = referralQuery.data;
  const inviteLink = referral?.link ?? null;
  const numbers = new Intl.NumberFormat(localeOf(language));
  // A zero balance would divide by zero; the bar is empty in that case anyway.
  const meterTotal = Math.max(me.balance, 1);
  const availableWidth = Math.round((me.available / meterTotal) * 100);
  const reservedWidth = Math.round((me.reserved / meterTotal) * 100);

  async function copyReferralLink(link: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard is unavailable in some Telegram webviews; the link stays selectable.
    }
  }

  return (
    <section className="profile-page rise">
      <header className="page-masthead">
        <p className="eyebrow">{tx("profile.eyebrow")}</p>
        <h1>{tx("profile.title")}</h1>
        <p>{tx("profile.subtitle")}</p>
      </header>

      <article className="profile-identity">
        <span className="profile-avatar" aria-hidden>{identity}</span>
        <div>
          <span className="micro-label">{plan}</span>
          <h2>{me.username ? `@${me.username}` : tx("profile.anonymous")}</h2>
          <p>Telegram ID · {me.telegram_id}</p>
        </div>
        <span className="profile-verified"><Icon name="check" /></span>
      </article>

      <section className="pf-wallet" aria-labelledby="pf-wallet-title">
        <header>
          <div>
            <p className="eyebrow">{tx("profile.walletEyebrow")}</p>
            <h2 id="pf-wallet-title">{tx("profile.walletTitle")}</h2>
          </div>
          {me.reserved > 0 ? (
            <span className="pf-wallet-active">
              {activeCount > 0
                ? `${activeCount} ${profileText(language, "walletActive")}`
                : profileText(language, "walletReserved")}
            </span>
          ) : null}
        </header>

        <p className="pf-wallet-figure">
          <strong>{numbers.format(me.available)}</strong>
          <span>{profileText(language, "walletAvailable")}</span>
        </p>

        <div
          className="pf-meter"
          role="img"
          aria-label={`${me.available} / ${me.balance}`}
        >
          <i className="is-available" style={{ width: `${availableWidth}%` }} />
          <i className="is-reserved" style={{ width: `${reservedWidth}%` }} />
        </div>

        <dl className="pf-wallet-legend">
          <div>
            <dt><i className="is-available" aria-hidden />{tx("profile.available")}</dt>
            <dd>{numbers.format(me.available)}</dd>
          </div>
          <div>
            <dt><i className="is-reserved" aria-hidden />{tx("profile.reserved")}</dt>
            <dd>{numbers.format(me.reserved)}</dd>
          </div>
          <div>
            <dt><i aria-hidden />{profileText(language, "walletTotal")}</dt>
            <dd>{numbers.format(me.balance)}</dd>
          </div>
        </dl>

        {me.reserved > 0 ? (
          <p className="pf-wallet-hint">{profileText(language, "walletReservedHint")}</p>
        ) : null}

        <div className="pf-wallet-actions">
          <Link to="/plans" className="pf-btn is-primary">
            {tx("profile.topUp")}
          </Link>
          <Link to="/history" className="pf-btn">
            {profileText(language, "walletHistory")}
          </Link>
          <Link to="/wallet" className="pf-btn">
            {tx("wallet.title")}
          </Link>
        </div>
      </section>

      <section className="pf-activity" aria-labelledby="pf-activity-title">
        <header className="profile-section-title">
          <span><Icon name="history" /></span>
          <div>
            <p className="eyebrow">{profileText(language, "activityEyebrow")}</p>
            <h2 id="pf-activity-title">{profileText(language, "activityTitle")}</h2>
          </div>
          <Link to="/history" className="pf-link">
            {profileText(language, "activityAll")} <Icon name="arrow" />
          </Link>
        </header>

        {history.length ? (
          <>
            <div className="pf-stats">
              <div>
                <strong>{numbers.format(activity.images)}</strong>
                <span>{profileText(language, "activityImages")}</span>
              </div>
              <div>
                <strong>{numbers.format(activity.videos)}</strong>
                <span>{profileText(language, "activityVideos")}</span>
              </div>
              <div>
                <strong>{numbers.format(activity.credits)}</strong>
                <span>{profileText(language, "activityCredits")}</span>
              </div>
            </div>
            <div className="pf-works">
              {recentWorks.map((item) => (
                <RecentWork
                  key={item.id}
                  item={item}
                  language={language}
                  preview={
                    item.preview_asset_id
                      ? previewById.get(item.preview_asset_id)
                      : undefined
                  }
                />
              ))}
            </div>
          </>
        ) : (
          <div className="pf-activity-empty">
            <p>{profileText(language, "activityEmpty")}</p>
            <Link to="/create" className="pf-btn is-primary">
              {profileText(language, "activityStart")}
            </Link>
          </div>
        )}
      </section>

      <section className="pf-referral" aria-labelledby="pf-referral-title">
        <header className="profile-section-title">
          <span><Icon name="star" /></span>
          <div>
            <p className="eyebrow">{profileText(language, "referralEyebrow")}</p>
            <h2 id="pf-referral-title">{profileText(language, "referralTitle")}</h2>
          </div>
        </header>

        {referral?.enabled ? (
          <>
            <div className="pf-stats">
              <div>
                <strong>{numbers.format(referral.invited_count)}</strong>
                <span>{profileText(language, "referralInvited")}</span>
              </div>
              <div>
                <strong>{numbers.format(referral.credited_bonus_credits)}</strong>
                <span>{profileText(language, "referralEarned")}</span>
              </div>
              <div>
                <strong>{numbers.format(referral.pending_rewards_count)}</strong>
                <span>{profileText(language, "referralPending")}</span>
              </div>
            </div>

            {inviteLink ? (
              <div className="pf-invite-link">
                <code>{inviteLink}</code>
                <button type="button" onClick={() => void copyReferralLink(inviteLink)}>
                  {copied
                    ? profileText(language, "referralCopied")
                    : profileText(language, "referralCopy")}
                </button>
              </div>
            ) : null}

            <p className="pf-referral-terms">
              {profileText(language, "referralReward", {
                inviter: referral.inviter_bonus_credits,
                invitee: referral.invitee_bonus_credits,
              })}{" "}
              {profileText(language, "referralCondition", {
                stars: referral.minimum_purchase_stars,
                hours: referral.waiting_period_hours,
              })}
            </p>
          </>
        ) : (
          <div className="pf-activity-empty">
            <p>
              <strong>{profileText(language, "referralOff")}</strong>
              <small>{profileText(language, "referralOffHint")}</small>
            </p>
          </div>
        )}
      </section>

      <section className="profile-preferences" aria-labelledby="profile-preferences-title">
        <header className="profile-section-title">
          <span><Icon name="settings" /></span>
          <div>
            <p className="eyebrow">{tx("profile.preferencesEyebrow")}</p>
            <h2 id="profile-preferences-title">{tx("profile.preferencesTitle")}</h2>
          </div>
        </header>

        <div className="profile-setting language-setting">
          <span className="setting-icon"><Icon name="language" /></span>
          <div>
            <strong>{tx("profile.language")}</strong>
            <small>{tx("profile.languageHelp")}</small>
          </div>
          <div className="language-switch" role="group" aria-label={tx("profile.language")}>
            {(["kk", "ru"] as Language[]).map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={language === item}
                className={language === item ? "active" : ""}
                disabled={languageMutation.isPending}
                onClick={() => {
                  setLanguage(item);
                  languageMutation.mutate(item);
                }}
              >
                {item.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="profile-setting">
          <span className="setting-icon"><Icon name="bell" /></span>
          <div>
            <strong id="profile-ready-notifications-label">{tx("profile.readyNotifications")}</strong>
            <small id="profile-ready-notifications-help">{tx("profile.readyNotificationsHelp")}</small>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={me.notify_generation_ready}
            aria-labelledby="profile-ready-notifications-label"
            aria-describedby="profile-ready-notifications-help"
            className={`profile-switch${me.notify_generation_ready ? " is-on" : ""}`}
            disabled={notificationMutation.isPending}
            onClick={() => {
              notificationMutation.reset();
              notificationMutation.mutate(!me.notify_generation_ready);
            }}
          >
            <span aria-hidden />
          </button>
        </div>
        {notificationMutation.isError ? (
          <p className="notification-error" role="alert">
            {tx("profile.notificationUpdateError")}
          </p>
        ) : null}
      </section>

      <section className="profile-trust" aria-labelledby="profile-trust-title">
        <header className="profile-section-title">
          <span><Icon name="support" /></span>
          <div>
            <p className="eyebrow">{tx("profile.trustEyebrow")}</p>
            <h2 id="profile-trust-title">{tx("profile.trustTitle")}</h2>
          </div>
        </header>
        <div className="profile-trust-list">
          <Link to="/invite">
            <Icon name="star" />
            <span>
              <strong>{tx("profile.invite")}</strong>
              <small>{tx("profile.inviteHelp")}</small>
            </span>
            <Icon name="arrow" />
          </Link>
          <Link to="/support" className="profile-support-row">
            <Icon name="support" />
            <span>
              <strong>{tx("profile.support")}</strong>
              <small>{tx("profile.supportHelp")}</small>
            </span>
            <code>/support</code>
            <Icon name="arrow" />
          </Link>
          <Link to="/plans">
            <Icon name="wallet" />
            <span>
              <strong>{tx("profile.purchases")}</strong>
              <small>{tx("profile.purchasesHelp")}</small>
            </span>
            <Icon name="arrow" />
          </Link>
          {productsQuery.data?.terms_url ? (
            <a href={productsQuery.data.terms_url} target="_blank" rel="noreferrer">
              <Icon name="history" />
              <span>
                <strong>{tx("profile.terms")}</strong>
                <small>{tx("profile.termsHelp")}</small>
              </span>
              <Icon name="arrow" />
            </a>
          ) : null}
          {productsQuery.data?.refund_policy_url ? (
            <a
              href={productsQuery.data.refund_policy_url}
              target="_blank"
              rel="noreferrer"
            >
              <Icon name="repeat" />
              <span>
                <strong>{profileText(language, "refundPolicy")}</strong>
                <small>{profileText(language, "refundPolicyHelp")}</small>
              </span>
              <Icon name="arrow" />
            </a>
          ) : null}
        </div>
      </section>
    </section>
  );
}
