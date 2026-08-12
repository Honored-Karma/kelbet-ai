import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../shared/api/client";
import type { CreditTransaction } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import type { MessageKey } from "../shared/i18n/messages";
import { ErrorState } from "../shared/ui/ErrorState";
import { Icon } from "../shared/ui/Icon";
import { SkeletonBlock } from "../shared/ui/Skeleton";

const PAGE = 50;
/** Предел, объявленный сервером на `limit` в GET /wallet/transactions. */
const MAX = 200;

const REASON_KEYS: Record<string, MessageKey> = {
  welcome_bonus: "wallet.reasonWelcomeBonus",
  ai_chat: "wallet.reasonAiChat",
  prompt_assistant: "wallet.reasonPromptAssistant",
  generation_capture: "wallet.reasonGenerationCapture",
  generation_refund: "wallet.reasonGenerationRefund",
  admin_adjust: "wallet.reasonAdminAdjust",
  plan_grant: "wallet.reasonPlanGrant",
  payment_purchase: "wallet.reasonPaymentPurchase",
  payment_refund: "wallet.reasonPaymentRefund",
  referral_reward: "wallet.reasonReferralReward",
};

export function WalletPage() {
  const { tx, language } = useI18n();
  const [limit, setLimit] = useState(PAGE);

  const numbers = new Intl.NumberFormat(language === "kk" ? "kk-KZ" : "ru-RU");
  const dates = new Intl.DateTimeFormat(language === "kk" ? "kk-KZ" : "ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  const ledgerQuery = useQuery({
    queryKey: ["wallet-transactions", limit],
    queryFn: () => api.walletTransactions(limit),
  });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });

  if (ledgerQuery.isLoading) return <SkeletonBlock rows={6} />;
  if (ledgerQuery.isError) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void ledgerQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }

  const items = ledgerQuery.data ?? [];
  const canLoadMore = items.length >= limit && limit < MAX;

  function reasonLabel(row: CreditTransaction): string {
    const key = REASON_KEYS[row.reason];
    // Неизвестная причина показывается как есть: придумать ей название значило бы
    // соврать о том, за что списаны деньги.
    return key ? tx(key) : row.reason;
  }

  return (
    <section className="ledger-page rise">
      <header className="ledger-header">
        <p className="eyebrow">{tx("wallet.eyebrow")}</p>
        <h1>{tx("wallet.title")}</h1>
        <p className="ledger-lede">{tx("wallet.subtitle")}</p>
      </header>

      {meQuery.data ? (
        <dl className="ledger-summary">
          <div>
            <dt>{tx("profile.available")}</dt>
            <dd>{numbers.format(meQuery.data.available)}</dd>
          </div>
          <div>
            <dt>{tx("profile.reserved")}</dt>
            <dd>{numbers.format(meQuery.data.reserved)}</dd>
          </div>
        </dl>
      ) : null}

      {items.length === 0 ? (
        <div className="panel state-card">
          <h2>{tx("wallet.empty")}</h2>
          <p className="muted">{tx("wallet.emptyHint")}</p>
          <Link className="btn" to="/create">
            <Icon name="image" />
            {tx("generation.createImage")}
          </Link>
        </div>
      ) : (
        <ol className="ledger-list">
          {items.map((row) => {
            const credited = row.amount > 0;
            return (
              <li key={row.id} className="ledger-row">
                <div className="ledger-row-main">
                  <span className="ledger-reason">{reasonLabel(row)}</span>
                  <span className={`ledger-amount${credited ? " is-credit" : ""}`}>
                    {`${credited ? "+" : "−"}${numbers.format(Math.abs(row.amount))}`}
                  </span>
                </div>
                <div className="ledger-row-meta">
                  <span>{dates.format(new Date(row.created_at))}</span>
                  <span>{`${tx("wallet.balanceAfter")} ${numbers.format(row.balance_after)}`}</span>
                </div>
                {row.generation_id ? (
                  <Link className="ledger-link" to={`/generations/${row.generation_id}`}>
                    {tx("wallet.openGeneration")}
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      {canLoadMore ? (
        <button
          type="button"
          className="btn btn-ghost btn-block"
          disabled={ledgerQuery.isFetching}
          onClick={() => setLimit((current) => Math.min(MAX, current + PAGE))}
        >
          {ledgerQuery.isFetching ? tx("common.loading") : tx("wallet.showMore")}
        </button>
      ) : null}
    </section>
  );
}
