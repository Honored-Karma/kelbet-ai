import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../shared/api/client";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

export function InvitePage() {
  const { tx } = useI18n();
  const [copied, setCopied] = useState(false);
  const summaryQuery = useQuery({
    queryKey: ["referrals", "me"],
    queryFn: () => api.getReferralSummary(),
  });

  if (summaryQuery.isLoading) return <SkeletonBlock rows={5} />;
  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void summaryQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }

  const summary = summaryQuery.data;
  if (!summary.enabled || !summary.link) {
    return (
      <section className="invite-page rise">
        <header className="page-masthead">
          <p className="eyebrow">{tx("invite.eyebrow")}</p>
          <h1>{tx("invite.title")}</h1>
          <p>{tx("invite.disabled")}</p>
        </header>
        <article className="invite-disabled"><Icon name="star" /></article>
      </section>
    );
  }
  const referralLink = summary.link;

  const copyLink = async () => {
    await navigator.clipboard.writeText(referralLink);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  const shareLink = async () => {
    if (navigator.share) {
      await navigator.share({ title: "KELBET AI", text: tx("invite.shareText"), url: referralLink });
      return;
    }
    await copyLink();
  };

  return (
    <section className="invite-page rise">
      <header className="page-masthead">
        <p className="eyebrow">{tx("invite.eyebrow")}</p>
        <h1>{tx("invite.title")}</h1>
        <p>{tx("invite.subtitle")}</p>
      </header>

      <article className="invite-link-card">
        <span className="micro-label">{tx("invite.personalLink")}</span>
        <code>{referralLink}</code>
        <div>
          <button type="button" className="btn btn-secondary" onClick={() => void copyLink()}>
            {copied ? tx("invite.copied") : tx("invite.copy")}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void shareLink()}>
            {tx("invite.share")}
          </button>
        </div>
      </article>

      <section className="invite-stats" aria-label={tx("invite.stats") }>
        <article><span>{tx("invite.invited")}</span><strong>{summary.invited_count}</strong></article>
        <article><span>{tx("invite.pending")}</span><strong>{summary.pending_rewards_count}</strong></article>
        <article><span>{tx("invite.credited")}</span><strong>{summary.credited_bonus_credits}</strong></article>
      </section>

      <article className="invite-terms">
        <h2>{tx("invite.terms")}</h2>
        <p>
          {tx("invite.termsBody")
            .replace("{bonus}", String(summary.inviter_bonus_credits))
            .replace("{friendBonus}", String(summary.invitee_bonus_credits))
            .replace("{minimum}", String(summary.minimum_purchase_stars))
            .replace("{waiting}", String(summary.waiting_period_hours))}
        </p>
        <small>{tx("invite.safety")}</small>
      </article>
    </section>
  );
}
