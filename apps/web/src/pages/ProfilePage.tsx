import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../shared/api/client";
import type { Language, Me } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

export function ProfilePage() {
  const { tx, language, setLanguage } = useI18n();
  const queryClient = useQueryClient();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const productsQuery = useQuery({
    queryKey: ["payment-products"],
    queryFn: () => api.listPaymentProducts(),
    retry: 1,
  });

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

      <section className="profile-wallet" aria-labelledby="profile-wallet-title">
        <header>
          <div>
            <p className="eyebrow">{tx("profile.walletEyebrow")}</p>
            <h2 id="profile-wallet-title">{tx("profile.walletTitle")}</h2>
          </div>
          <Link to="/plans">{tx("profile.topUp")} <Icon name="arrow" /></Link>
        </header>
        <div className="wallet-balance">
          <span><i aria-hidden>◆</i>{tx("profile.available")}</span>
          <strong>{me.available}</strong>
        </div>
        <dl>
          <div>
            <dt>{tx("profile.balance")}</dt>
            <dd>{me.balance}</dd>
          </div>
          <div>
            <dt>{tx("profile.reserved")}</dt>
            <dd>{me.reserved}</dd>
          </div>
        </dl>
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
            {(["ru", "kk"] as Language[]).map((item) => (
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
            <strong>{tx("profile.readyNotifications")}</strong>
            <small>{tx("profile.readyNotificationsHelp")}</small>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={me.notify_generation_ready}
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
        </div>
      </section>
    </section>
  );
}
