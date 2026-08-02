import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../shared/api/client";
import type { PaymentOrder } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";
import { getTelegramWebApp } from "../shared/telegram/webapp";
import { ErrorState } from "../shared/ui/ErrorState";
import { SkeletonBlock } from "../shared/ui/Skeleton";

type OrderStatusKey =
  | "plans.pending"
  | "plans.paid"
  | "plans.cancelled"
  | "plans.refunded"
  | "plans.disputed"
  | "plans.expired";

function orderStatus(
  order: PaymentOrder,
  tx: (key: OrderStatusKey) => string,
): { label: string; tone: "paid" | "pending" | "cancelled" | "refunded" | "disputed" } {
  if (order.status === "paid") return { label: tx("plans.paid"), tone: "paid" };
  if (order.status === "refunded") return { label: tx("plans.refunded"), tone: "refunded" };
  if (order.status === "disputed") return { label: tx("plans.disputed"), tone: "disputed" };
  if (order.status === "expired") return { label: tx("plans.expired"), tone: "cancelled" };
  if (order.status === "cancelled") return { label: tx("plans.cancelled"), tone: "cancelled" };
  return { label: tx("plans.pending"), tone: "pending" };
}

export function PlansPage() {
  const { tx } = useI18n();
  const queryClient = useQueryClient();
  const [accepted, setAccepted] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingProductSlug, setPendingProductSlug] = useState<string | null>(null);
  const [activeOrderId, setActiveOrderId] = useState<string | null>(null);
  const productsQuery = useQuery({
    queryKey: ["payment-products"],
    queryFn: () => api.listPaymentProducts(),
  });
  const historyQuery = useQuery({
    queryKey: ["payment-history"],
    queryFn: () => api.paymentHistory(),
    refetchInterval: activeOrderId ? 2_000 : false,
  });
  useEffect(() => {
    if (!activeOrderId) return;
    const order = historyQuery.data?.find((item) => item.id === activeOrderId);
    if (order && order.status !== "pending") {
      setActiveOrderId(null);
      if (order.status === "paid") void queryClient.invalidateQueries({ queryKey: ["me"] });
    }
  }, [activeOrderId, historyQuery.data, queryClient]);
  useEffect(() => {
    if (!activeOrderId) return;
    const timeout = window.setTimeout(() => setActiveOrderId(null), 45_000);
    return () => window.clearTimeout(timeout);
  }, [activeOrderId]);
  const orderMutation = useMutation({
    mutationFn: (productSlug: string) =>
      api.createPaymentOrder({
        productSlug,
        termsAccepted: accepted,
        termsVersion: productsQuery.data?.terms_version ?? "",
        idempotencyKey: crypto.randomUUID(),
      }),
    onSuccess: (order) => {
      setNotice(null);
      void queryClient.invalidateQueries({ queryKey: ["payment-history"] });
      if (!order.invoice_url) {
        setNotice(tx("plans.invoiceFailed"));
        return;
      }
      setActiveOrderId(order.id);
      const webApp = getTelegramWebApp();
      if (webApp?.openInvoice) {
        webApp.openInvoice(order.invoice_url, (status) => {
          setActiveOrderId(order.id);
          void queryClient.invalidateQueries({ queryKey: ["payment-history"] });
          if (status === "paid") {
            void queryClient.invalidateQueries({ queryKey: ["payment-history"] });
            void queryClient.invalidateQueries({ queryKey: ["me"] });
          }
        });
      } else {
        window.open(order.invoice_url, "_blank", "noopener,noreferrer");
      }
    },
    onError: () => setNotice(tx("plans.invoiceFailed")),
    onSettled: () => setPendingProductSlug(null),
  });
  const reopenMutation = useMutation({
    mutationFn: (orderId: string) => api.reopenPaymentOrder(orderId),
    onSuccess: (order) => {
      if (!order.invoice_url) return;
      setActiveOrderId(order.id);
      const webApp = getTelegramWebApp();
      if (webApp?.openInvoice) {
        webApp.openInvoice(order.invoice_url, () => {
          void queryClient.invalidateQueries({ queryKey: ["payment-history"] });
        });
      } else {
        window.open(order.invoice_url, "_blank", "noopener,noreferrer");
      }
    },
    onError: () => setNotice(tx("plans.invoiceFailed")),
  });

  if (productsQuery.isLoading) return <SkeletonBlock rows={6} />;
  if (productsQuery.isError || !productsQuery.data) {
    return (
      <ErrorState
        title={tx("common.error")}
        onRetry={() => void productsQuery.refetch()}
        retryLabel={tx("common.retry")}
      />
    );
  }

  const data = productsQuery.data;
  return (
    <section className="rise payment-page" aria-labelledby="plans-title">
      <header className="payment-hero">
        <div className="payment-hero-orbit" aria-hidden="true">
          <span>★</span>
          <small>XTR</small>
        </div>
        <div className="payment-hero-copy">
          <span className="payment-badge">
            <span aria-hidden="true">★</span>
            {tx("plans.badge")}
          </span>
          <h1 id="plans-title">{tx("plans.title")}</h1>
          <p>{tx("plans.body")}</p>
        </div>
        <div className="payment-note">
          <span className="payment-note-mark" aria-hidden="true">✓</span>
          <p>{tx("plans.subtitle")}</p>
        </div>
      </header>

      {!data.payments_enabled ? (
        <div className="payment-warning" role="status">
          <span aria-hidden="true">!</span>
          <p>{tx("plans.unavailable")}</p>
        </div>
      ) : null}

      <div className="payment-grid" aria-label={tx("plans.title")}>
        {data.items.map((product, index) => (
          <article className={`payment-card${index === 1 ? " featured" : ""}`} key={product.slug}>
            <div className="payment-card-copy">
              <header className="payment-card-header">
                <span className="payment-card-index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="payment-card-labels">
                  <span className="micro-label">{product.name}</span>
                  {index === 1 ? <span className="payment-recommended">{tx("plans.recommended")}</span> : null}
                </div>
              </header>
              <div className="payment-amount">
                <strong>{product.credits}</strong>
                <span>{tx("plans.credits")}</span>
              </div>
              <p className="payment-description">{product.description}</p>
            </div>
            <div className="payment-card-action">
              <div className="payment-stars-price" aria-label={`${product.stars} Telegram Stars`}>
                <span aria-hidden="true">★</span>
                <strong>{product.stars}</strong>
                <small>Telegram Stars</small>
              </div>
              <button
                className="payment-buy-button"
                type="button"
                disabled={!data.payments_enabled || !accepted || orderMutation.isPending}
                aria-busy={pendingProductSlug === product.slug}
                aria-describedby="payment-terms-hint"
                onClick={() => {
                  if (!accepted) {
                    setNotice(tx("plans.termsRequired"));
                    return;
                  }
                  setNotice(null);
                  setPendingProductSlug(product.slug);
                  orderMutation.mutate(product.slug);
                }}
              >
                <span>
                  {pendingProductSlug === product.slug
                    ? tx("plans.opening")
                    : tx("plans.pay").replace("{stars}", String(product.stars))}
                </span>
                <span aria-hidden="true">↗</span>
              </button>
            </div>
          </article>
        ))}
      </div>

      <section className={`payment-consent${accepted ? " is-accepted" : ""}`} aria-labelledby="payment-terms-title">
        <div className="payment-terms-control">
          <input
            id="payment-terms"
            type="checkbox"
            checked={accepted}
            onChange={(event) => {
              setAccepted(event.target.checked);
              setNotice(null);
            }}
          />
          <label htmlFor="payment-terms" id="payment-terms-title">
            <span className="payment-checkbox" aria-hidden="true">✓</span>
            <span>{tx("plans.terms")}</span>
          </label>
        </div>
        <a className="payment-terms-link" href={data.terms_url} target="_blank" rel="noreferrer">
          {tx("plans.openTerms")}
          <span aria-hidden="true">↗</span>
        </a>
        <a className="payment-terms-link" href={data.refund_policy_url} target="_blank" rel="noreferrer">
          {tx("plans.refundPolicy")} <span aria-hidden="true">↗</span>
        </a>
        <p className="payment-terms-hint" id="payment-terms-hint">
          {accepted ? tx("plans.termsAccepted") : tx("plans.termsRequired")}
        </p>
      </section>

      <p className="payment-confirmation-note" role="note">
        <span aria-hidden="true">✓</span> {tx("plans.confirmation")}
        {activeOrderId ? <strong>{tx("plans.checking")}</strong> : null}
      </p>

      {notice ? (
        <div className="payment-error" role="alert">
          <span aria-hidden="true">!</span>
          <p>{notice}</p>
        </div>
      ) : null}

      <section className="payment-history-section" aria-labelledby="payment-history-title">
        <header className="payment-history-heading">
          <div>
            <span className="eyebrow">KELBET / XTR</span>
            <h2 id="payment-history-title">{tx("plans.history")}</h2>
          </div>
          {historyQuery.data?.length ? <span className="payment-history-count">{historyQuery.data.length}</span> : null}
        </header>

        {historyQuery.isLoading ? (
          <div className="payment-history payment-history-loading" aria-label={tx("common.loading")}>
            <SkeletonBlock rows={3} />
          </div>
        ) : historyQuery.isError ? (
          <div className="payment-history-state" role="alert">
            <p>{tx("common.error")}</p>
            <button
              className="payment-history-retry"
              type="button"
              onClick={() => void historyQuery.refetch()}
            >
              {tx("common.retry")}
            </button>
          </div>
        ) : historyQuery.data?.length ? (
          <ol className="payment-history">
            {historyQuery.data.slice(0, 8).map((order) => {
              const status = orderStatus(order, tx);
              return (
                <li className="payment-history-row" key={order.id}>
                  <div className="payment-history-product">
                    <strong>{order.product_name}</strong>
                    <span>{order.credits} {tx("plans.credits")}</span>
                    <small>{tx("plans.reference")}: {order.support_reference}</small>
                  </div>
                  <div className="payment-history-payment">
                    <strong><span aria-hidden="true">★</span> {order.total_amount}</strong>
                    <span className={`payment-status is-${status.tone}`}>
                      <span aria-hidden="true" />
                      {status.label}
                    </span>
                    {order.status === "pending" ? (
                      <button
                        className="payment-history-retry"
                        type="button"
                        disabled={reopenMutation.isPending}
                        onClick={() => reopenMutation.mutate(order.id)}
                      >
                        {tx("plans.resume")}
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="payment-history-state is-empty">
            <span aria-hidden="true">—</span>
            <div>
              <strong>{tx("plans.emptyHistory")}</strong>
              <p>{tx("plans.body")}</p>
            </div>
          </div>
        )}
      </section>
      <nav className="payment-help-links" aria-label={tx("plans.support")}>
        <a href={data.support_url} target="_blank" rel="noreferrer">{tx("plans.support")}</a>
        <a href={data.refund_policy_url} target="_blank" rel="noreferrer">{tx("plans.refundPolicy")}</a>
      </nav>
    </section>
  );
}
