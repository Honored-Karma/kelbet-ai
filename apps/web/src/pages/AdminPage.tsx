import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { currentAppPath } from "../app/navigation";
import { adminApi } from "../features/admin/client";
import { AdminCapabilityGate } from "../features/admin/CapabilityGate";
import { adminMessage, type AdminMessageKey } from "../features/admin/messages";
import { canRenderAdminAction, hasAdminWriteCapability } from "../features/admin/permissions";
import {
  isPaymentRefundRetryable,
  isValidAdminUuid,
  safeIssueDetails,
} from "../features/admin/reconciliation";
import type {
  AdminGeneration,
  AdminModerationDecision,
  AdminMe,
  AdminPaymentOrder,
  AdminReferralReward,
  AdminUser,
  AuditEvent,
  SafeActionInput,
  ModerationReviewOutcome,
  ReconciliationIssueStatus,
} from "../features/admin/types";
import { getToken, setToken } from "../shared/api/client";
import { ApiError, type Language } from "../shared/api/types";
import { useI18n } from "../shared/i18n/runtime";

type AdminSection = "users" | "controls" | "moderation" | "reconciliation" | "referrals" | "audit";
type UserActivity = "ledger" | "generations" | "payments";

type PendingAction = {
  actionId: string;
  title: string;
  description: string;
  run: (actionId: string) => Promise<AuditEvent>;
};

type RequestAction = (action: Omit<PendingAction, "actionId">) => void;

const SAFE_CODE = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,63}$/;

function shortId(value: string): string {
  return value.length > 15 ? `${value.slice(0, 8)}…${value.slice(-5)}` : value;
}

function formatDate(value: string | null, language: Language = "ru"): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat(language === "kk" ? "kk-KZ" : "ru-RU", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
}

function statusTone(status: string): "ok" | "danger" | "pending" {
  const normalized = status.toLowerCase();
  if (["active", "paid", "succeeded", "captured", "enabled", "refunded", "resolved", "completed"].includes(normalized)) return "ok";
  if (["failed", "blocked", "block", "cancelled", "disabled", "needs_review", "critical"].includes(normalized)) return "danger";
  return "pending";
}

function reconciliationLabel(
  value: string,
  t: (key: AdminMessageKey) => string,
): string {
  const labels: Partial<Record<string, AdminMessageKey>> = {
    open: "openStatus",
    resolved: "resolvedStatus",
    needs_review: "needsReviewStatus",
    requested: "requestedStatus",
    processing: "processingStatus",
    refunded: "refundedStatus",
    failed: "failedStatus",
    completed: "completedStatus",
    critical: "criticalSeverity",
    warning: "warningSeverity",
    pending: "pendingReferralStatus",
    eligible: "eligibleReferralStatus",
    credited: "creditedReferralStatus",
    cancelled: "cancelledReferralStatus",
  };
  const key = labels[value.toLowerCase()];
  return key ? t(key) : value;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function AdminState({
  code,
  title,
  body,
  action,
}: {
  code: string;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <main className="admin-gate">
      <section className="admin-gate-card" aria-labelledby="admin-state-title">
        <span className="admin-gate-code" aria-hidden>{code}</span>
        <p className="admin-kicker">KELBET / OPS</p>
        <h1 id="admin-state-title">{title}</h1>
        <p>{body}</p>
        {action ? <div className="admin-gate-action">{action}</div> : null}
      </section>
    </main>
  );
}

function Status({ children, tone }: { children: ReactNode; tone: "ok" | "danger" | "pending" }) {
  return <span className={`admin-status is-${tone}`}>{children}</span>;
}

function SafeCodes({
  value,
  onChange,
  t,
  idPrefix,
}: {
  value: SafeActionInput;
  onChange: (value: SafeActionInput) => void;
  t: (key: AdminMessageKey) => string;
  idPrefix: string;
}) {
  return (
    <div className="admin-action-codes">
      <label className="admin-field" htmlFor={`${idPrefix}-reason`}>
        <span>{t("reason")}</span>
        <input
          id={`${idPrefix}-reason`}
          value={value.reason}
          onChange={(event) => onChange({ ...value, reason: event.target.value })}
          placeholder="support_case"
          pattern="[A-Za-z0-9][A-Za-z0-9._:-]{2,63}"
          required
          autoComplete="off"
        />
      </label>
      <label className="admin-field" htmlFor={`${idPrefix}-reference`}>
        <span>{t("reference")}</span>
        <input
          id={`${idPrefix}-reference`}
          value={value.reference}
          onChange={(event) => onChange({ ...value, reference: event.target.value })}
          placeholder="ticket:KBT-1042"
          pattern="[A-Za-z0-9][A-Za-z0-9._:-]{2,63}"
          required
          autoComplete="off"
        />
      </label>
    </div>
  );
}

function codesValid(value: SafeActionInput): boolean {
  return SAFE_CODE.test(value.reason) && SAFE_CODE.test(value.reference);
}

function ConfirmDialog({
  action,
  busy,
  error,
  onConfirm,
  onCancel,
  t,
}: {
  action: PendingAction;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  t: (key: AdminMessageKey) => string;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const frame = requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("[data-confirm-primary]")?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, []);

  function handleKeyDown(event: ReactKeyboardEvent<HTMLDialogElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!busy) onCancel();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ) ?? [],
    );
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="admin-confirm"
      open
      aria-modal="true"
      aria-labelledby="admin-confirm-title"
      aria-describedby="admin-confirm-description"
      onKeyDown={handleKeyDown}
    >
      <div className="admin-confirm-mark" aria-hidden>!</div>
      <p className="admin-kicker">IDEMPOTENT ACTION</p>
      <h2 id="admin-confirm-title">{action.title}</h2>
      <p id="admin-confirm-description">{action.description}</p>
      <code title={action.actionId}>{shortId(action.actionId)}</code>
      {error ? <p className="admin-inline-error" role="alert">{error}</p> : null}
      <div className="admin-confirm-actions">
        <button type="button" className="admin-button is-muted" onClick={onCancel} disabled={busy}>
          {t("cancel")}
        </button>
        <button type="button" className="admin-button is-danger" onClick={onConfirm} disabled={busy} data-confirm-primary>
          {busy ? "…" : t("confirm")}
        </button>
      </div>
    </dialog>
  );
}

function AdminHeader({ operator, t }: { operator: AdminMe; t: (key: AdminMessageKey) => string }) {
  const canWrite = hasAdminWriteCapability(operator);
  return (
    <header className="admin-header">
      <div className="admin-brand-lockup">
        <span className="admin-brand-mark" aria-hidden>K</span>
        <div>
          <strong>KELBET</strong>
          <span>{t("product")}</span>
        </div>
      </div>
      <div className="admin-operator">
        <div>
          <strong>{operator.username ? `@${operator.username}` : operator.telegram_id}</strong>
          <span>{operator.bootstrap ? "bootstrap · " : ""}{operator.role}</span>
        </div>
        <Status tone={canWrite ? "ok" : "pending"}>
          {canWrite ? t("writeAccess") : t("readOnly")}
        </Status>
      </div>
    </header>
  );
}

function AdminNav({
  section,
  onChange,
  t,
}: {
  section: AdminSection;
  onChange: (section: AdminSection) => void;
  t: (key: AdminMessageKey) => string;
}) {
  const items: { id: AdminSection; index: string; label: AdminMessageKey }[] = [
    { id: "users", index: "01", label: "users" },
    { id: "controls", index: "02", label: "controls" },
    { id: "moderation", index: "03", label: "moderation" },
    { id: "reconciliation", index: "04", label: "reconciliation" },
    { id: "referrals", index: "05", label: "referrals" },
    { id: "audit", index: "06", label: "audit" },
  ];
  return (
    <nav className="admin-nav" aria-label={t("product")}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={section === item.id ? "is-active" : ""}
          aria-current={section === item.id ? "page" : undefined}
          onClick={() => onChange(item.id)}
        >
          <span>{item.index}</span>
          {t(item.label)}
        </button>
      ))}
      <Link to="/" className="admin-back-link">↙ Mini App</Link>
    </nav>
  );
}

function QueryNotice({ text, error }: { text: string; error?: boolean }) {
  return <div className={`admin-query-notice${error ? " is-error" : ""}`} role={error ? "alert" : "status"}>{text}</div>;
}

function UserActivityPanel({
  user,
  operator,
  activity,
  onActivity,
  onAction,
  t,
}: {
  user: AdminUser;
  operator: AdminMe;
  activity: UserActivity;
  onActivity: (activity: UserActivity) => void;
  onAction: RequestAction;
  t: (key: AdminMessageKey) => string;
}) {
  const ledgerQuery = useQuery({
    queryKey: ["admin", "ledger", user.id],
    queryFn: () => adminApi.ledger(user.id),
    enabled: activity === "ledger",
  });
  const generationQuery = useQuery({
    queryKey: ["admin", "generations", user.id],
    queryFn: () => adminApi.generations(user.id),
    enabled: activity === "generations",
  });
  const paymentsQuery = useQuery({
    queryKey: ["admin", "payments", user.id],
    queryFn: () => adminApi.payments(user.id),
    enabled: activity === "payments",
  });
  const [refundCodes, setRefundCodes] = useState<SafeActionInput>({ reason: "", reference: "" });
  const canRefund = canRenderAdminAction(operator, "generation.refund");
  const canRefundPayment = canRenderAdminAction(operator, "payment.refund");

  function requestRefund(generation: AdminGeneration) {
    onAction({
      title: `${t("refund")} · ${shortId(generation.id)}`,
      description: `${generation.user_credit_price} кр. · ${refundCodes.reason} · ${refundCodes.reference}`,
      run: (actionId) => adminApi.refundGeneration(generation.id, refundCodes, actionId),
    });
  }

  function requestPaymentRefund(order: AdminPaymentOrder) {
    onAction({
      title: `${t("requestPaymentRefund")} · ${shortId(order.id)}`,
      description: `${order.total_amount} ${order.currency} · ${refundCodes.reason} · ${refundCodes.reference}`,
      run: (actionId) =>
        adminApi.requestPaymentRefund(order.id, refundCodes, actionId),
    });
  }

  return (
    <section className="admin-activity" aria-label="User activity">
      <div className="admin-tabs" role="tablist">
        {(["ledger", "generations", "payments"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activity === tab}
            className={activity === tab ? "is-active" : ""}
            onClick={() => onActivity(tab)}
          >
            {t(tab)}
          </button>
        ))}
      </div>

      {activity === "ledger" ? (
        ledgerQuery.isLoading ? <QueryNotice text={t("loading")} /> : ledgerQuery.isError ? (
          <QueryNotice error text={errorMessage(ledgerQuery.error, t("error"))} />
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr><th>Тип</th><th>Сумма</th><th>Баланс</th><th>Причина</th><th>Время</th></tr></thead>
              <tbody>
                {ledgerQuery.data?.map((row) => (
                  <tr key={row.id}>
                    <td><Status tone={row.amount >= 0 ? "ok" : "danger"}>{row.type}</Status></td>
                    <td className={row.amount >= 0 ? "admin-positive" : "admin-negative"}>{row.amount > 0 ? "+" : ""}{row.amount}</td>
                    <td>{row.balance_after}</td>
                    <td><code>{row.reason}</code></td>
                    <td>{formatDate(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!ledgerQuery.data?.length ? <QueryNotice text={t("empty")} /> : null}
          </div>
        )
      ) : null}

      {activity === "generations" ? (
        <>
          {canRefund ? (
            <div className="admin-refund-codes">
              <SafeCodes value={refundCodes} onChange={setRefundCodes} t={t} idPrefix="refund" />
              <p>{t("safeCodeHelp")}</p>
            </div>
          ) : null}
          {generationQuery.isLoading ? <QueryNotice text={t("loading")} /> : generationQuery.isError ? (
            <QueryNotice error text={errorMessage(generationQuery.error, t("error"))} />
          ) : (
            <div className="admin-record-list">
              {generationQuery.data?.map((generation) => {
                const refundable = generation.status.toLowerCase() === "succeeded" && Boolean(generation.reservation_id);
                return (
                  <article className="admin-record" key={generation.id}>
                    <div className="admin-record-main">
                      <Status tone={statusTone(generation.status)}>{generation.status}</Status>
                      <strong>{generation.provider} / {generation.provider_model_id}</strong>
                      <code title={generation.id}>{shortId(generation.id)}</code>
                    </div>
                    <dl className="admin-record-meta">
                      <div><dt>Цена</dt><dd>{generation.user_credit_price} кр.</dd></div>
                      <div><dt>Попытки</dt><dd>{generation.attempt_count}</dd></div>
                      <div><dt>Ошибка</dt><dd>{generation.error_code ?? "—"}</dd></div>
                      <div><dt>Создано</dt><dd>{formatDate(generation.created_at)}</dd></div>
                    </dl>
                    {canRefund && refundable ? (
                      <button
                        type="button"
                        className="admin-text-action is-danger"
                        disabled={!codesValid(refundCodes)}
                        onClick={() => requestRefund(generation)}
                      >
                        {t("refund")}
                      </button>
                    ) : null}
                  </article>
                );
              })}
              {!generationQuery.data?.length ? <QueryNotice text={t("empty")} /> : null}
            </div>
          )}
        </>
      ) : null}

      {activity === "payments" ? (
        <>
          {canRefundPayment ? (
            <div className="admin-refund-codes">
              <SafeCodes value={refundCodes} onChange={setRefundCodes} t={t} idPrefix="payment-order-refund" />
              <p>{t("safeCodeHelp")}</p>
            </div>
          ) : null}
          {paymentsQuery.isLoading ? <QueryNotice text={t("loading")} /> : paymentsQuery.isError ? (
            <QueryNotice error text={errorMessage(paymentsQuery.error, t("error"))} />
          ) : (
            <div className="admin-payment-columns">
            <section>
              <h3>{t("orders")}</h3>
              {paymentsQuery.data?.orders.map((order) => (
                <article className="admin-payment-row" key={order.id}>
                  <div><Status tone={statusTone(order.status)}>{order.status}</Status><strong>{order.product_slug}</strong></div>
                  <div><b>{order.total_amount} {order.currency}</b><span>{order.credits} кр.</span></div>
                  <small>{formatDate(order.created_at)} · {shortId(order.id)}</small>
                  {canRefundPayment && order.status.toLowerCase() === "paid" ? (
                    <button
                      type="button"
                      className="admin-text-action is-danger"
                      disabled={!codesValid(refundCodes)}
                      onClick={() => requestPaymentRefund(order)}
                    >
                      {t("requestPaymentRefund")}
                    </button>
                  ) : null}
                </article>
              ))}
              {!paymentsQuery.data?.orders.length ? <QueryNotice text={t("empty")} /> : null}
            </section>
            <section>
              <h3>{t("receipts")}</h3>
              {paymentsQuery.data?.receipts.map((receipt) => (
                <article className="admin-payment-row" key={receipt.id}>
                  <div><Status tone={statusTone(receipt.status)}>{receipt.status}</Status><strong>{shortId(receipt.id)}</strong></div>
                  <div><b>{receipt.total_amount} {receipt.currency}</b><span>{receipt.error_code ?? "OK"}</span></div>
                  <small>{formatDate(receipt.created_at)}</small>
                </article>
              ))}
              {!paymentsQuery.data?.receipts.length ? <QueryNotice text={t("empty")} /> : null}
            </section>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}

function UserWorkspace({
  operator,
  onAction,
  t,
}: {
  operator: AdminMe;
  onAction: RequestAction;
  t: (key: AdminMessageKey) => string;
}) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [activity, setActivity] = useState<UserActivity>("ledger");
  const [amount, setAmount] = useState("100");
  const [codes, setCodes] = useState<SafeActionInput>({ reason: "", reference: "" });
  const searchQuery = useQuery({
    queryKey: ["admin", "users", query],
    queryFn: () => adminApi.searchUsers(query),
    enabled: Boolean(query),
  });
  const userQuery = useQuery({
    queryKey: ["admin", "user", selectedUserId],
    queryFn: () => adminApi.getUser(selectedUserId ?? ""),
    enabled: Boolean(selectedUserId),
  });
  const canGrant = canRenderAdminAction(operator, "wallet.grant");
  const canBlock = canRenderAdminAction(operator, "user.block");
  const parsedAmount = Number(amount);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const clean = draft.trim().replace(/^@/, "");
    setSelectedUserId(null);
    setQuery(clean);
  }

  function requestGrant(user: AdminUser) {
    onAction({
      title: `${t("grant")} · ${user.username ? `@${user.username}` : user.telegram_id}`,
      description: `+${parsedAmount} кр. · ${codes.reason} · ${codes.reference}`,
      run: (actionId) => adminApi.grantCredits(user.id, parsedAmount, codes, actionId),
    });
  }

  function requestBlock(user: AdminUser) {
    const blocked = !user.is_blocked;
    onAction({
      title: `${blocked ? t("block") : t("unblock")} · ${user.username ? `@${user.username}` : user.telegram_id}`,
      description: `${codes.reason} · ${codes.reference}`,
      run: (actionId) => adminApi.setBlocked(user.id, blocked, codes, actionId),
    });
  }

  return (
    <div className="admin-users-layout">
      <aside className="admin-search-panel">
        <p className="admin-kicker">IDENTITY LOOKUP</p>
        <h1>{t("searchTitle")}</h1>
        <form className="admin-search-form" onSubmit={submitSearch}>
          <label htmlFor="admin-user-search">{t("searchHelp")}</label>
          <div>
            <input
              id="admin-user-search"
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="@username / 583… / UUID"
              autoComplete="off"
            />
            <button type="submit">{t("searchAction")}</button>
          </div>
        </form>
        <div className="admin-search-results" aria-live="polite">
          {!query ? <p>{t("emptySearch")}</p> : null}
          {searchQuery.isLoading ? <QueryNotice text={t("loading")} /> : null}
          {searchQuery.isError ? <QueryNotice error text={errorMessage(searchQuery.error, t("error"))} /> : null}
          {searchQuery.data?.map((user) => (
            <button
              type="button"
              key={user.id}
              className={selectedUserId === user.id ? "is-selected" : ""}
              onClick={() => setSelectedUserId(user.id)}
            >
              <span className="admin-avatar" aria-hidden>{(user.username?.[0] ?? "U").toUpperCase()}</span>
              <span><strong>{user.username ? `@${user.username}` : user.telegram_id}</strong><small>{shortId(user.id)}</small></span>
              <Status tone={user.is_blocked ? "danger" : "ok"}>{user.is_blocked ? "BLOCK" : "OK"}</Status>
            </button>
          ))}
          {searchQuery.data && !searchQuery.data.length ? <p>{t("noResults")}</p> : null}
        </div>
      </aside>

      <div className="admin-user-workspace">
        {!selectedUserId ? (
          <section className="admin-user-placeholder">
            <span aria-hidden>01</span>
            <h2>{t("profile")}</h2>
            <p>{t("emptySearch")}</p>
          </section>
        ) : userQuery.isLoading ? <QueryNotice text={t("loading")} /> : userQuery.isError ? (
          <QueryNotice error text={errorMessage(userQuery.error, t("error"))} />
        ) : userQuery.data ? (
          <>
            <section className="admin-user-profile">
              <div className="admin-user-title">
                <div>
                  <p className="admin-kicker">USER / {shortId(userQuery.data.id)}</p>
                  <h2>{userQuery.data.username ? `@${userQuery.data.username}` : userQuery.data.telegram_id}</h2>
                  <p>{userQuery.data.id}</p>
                </div>
                <Status tone={userQuery.data.is_blocked ? "danger" : "ok"}>
                  {userQuery.data.is_blocked ? t("blocked") : t("active")}
                </Status>
              </div>
              <dl className="admin-profile-facts">
                <div><dt>Telegram ID</dt><dd>{userQuery.data.telegram_id}</dd></div>
                <div><dt>Язык / план</dt><dd>{userQuery.data.language.toUpperCase()} · {userQuery.data.plan}</dd></div>
                <div><dt>Создан</dt><dd>{formatDate(userQuery.data.created_at)}</dd></div>
                <div><dt>Блокировка</dt><dd>{userQuery.data.blocked_reason ?? "—"}</dd></div>
              </dl>
              <div className="admin-wallet-strip">
                <div><span>{t("balance")}</span><strong>{userQuery.data.wallet?.balance ?? "—"}</strong></div>
                <div><span>{t("reserved")}</span><strong>{userQuery.data.wallet?.reserved ?? "—"}</strong></div>
                <div><span>{t("available")}</span><strong>{userQuery.data.wallet?.available ?? "—"}</strong></div>
                <small>ledger v{userQuery.data.wallet?.version ?? "—"}</small>
              </div>
            </section>

            {canGrant || canBlock ? (
              <section className="admin-user-actions" aria-label="Administrative actions">
                <div className="admin-section-heading"><div><p className="admin-kicker">CONTROLLED MUTATION</p><h3>Действия</h3></div><Status tone="danger">ADMIN</Status></div>
                <SafeCodes value={codes} onChange={setCodes} t={t} idPrefix="user-action" />
                <p className="admin-code-help">{t("safeCodeHelp")}</p>
                <div className="admin-action-row">
                  <AdminCapabilityGate operator={operator} action="wallet.grant">
                    <label className="admin-amount" htmlFor="admin-credit-amount">
                      <span>{t("amount")}</span>
                      <input id="admin-credit-amount" type="number" min="1" max="1000000" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} />
                      <button type="button" disabled={!codesValid(codes) || !Number.isInteger(parsedAmount) || parsedAmount < 1} onClick={() => requestGrant(userQuery.data)}>{t("grant")}</button>
                    </label>
                  </AdminCapabilityGate>
                  <AdminCapabilityGate operator={operator} action="user.block">
                    <button
                      type="button"
                      className="admin-button is-danger"
                      disabled={!codesValid(codes)}
                      onClick={() => requestBlock(userQuery.data)}
                    >
                      {userQuery.data.is_blocked ? t("unblock") : t("block")}
                    </button>
                  </AdminCapabilityGate>
                </div>
              </section>
            ) : (
              <div className="admin-readonly-note"><span aria-hidden>R/O</span><p><strong>{t("readOnly")}</strong> · Все изменения скрыты серверными capabilities.</p></div>
            )}

            <UserActivityPanel
              user={userQuery.data}
              operator={operator}
              activity={activity}
              onActivity={setActivity}
              onAction={onAction}
              t={t}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}

type ReconciliationFilter = "all" | ReconciliationIssueStatus;

function PaymentReconciliationView({
  operator,
  onAction,
  t,
  language,
}: {
  operator: AdminMe;
  onAction: RequestAction;
  t: (key: AdminMessageKey) => string;
  language: Language;
}) {
  const [filter, setFilter] = useState<ReconciliationFilter>("all");
  const [offset, setOffset] = useState(0);
  const [codes, setCodes] = useState<SafeActionInput>({ reason: "", reference: "" });
  const [orderId, setOrderId] = useState("");
  const canRefund = canRenderAdminAction(operator, "payment.refund");
  const reconciliationQuery = useQuery({
    queryKey: ["admin", "payment-reconciliation", filter, offset],
    queryFn: () => adminApi.reconciliation(filter === "all" ? undefined : filter, offset),
  });
  const filters: Array<{ id: ReconciliationFilter; label: AdminMessageKey }> = [
    { id: "all", label: "allStatuses" },
    { id: "open", label: "openStatus" },
    { id: "needs_review", label: "needsReviewStatus" },
    { id: "resolved", label: "resolvedStatus" },
  ];

  function requestRefund() {
    const cleanOrderId = orderId.trim();
    onAction({
      title: `${t("requestPaymentRefund")} · ${shortId(cleanOrderId)}`,
      description: `${codes.reason} · ${codes.reference}`,
      run: (actionId) =>
        adminApi.requestPaymentRefund(cleanOrderId, codes, actionId),
    });
  }

  function requestRetry(refundId: string, status: string) {
    onAction({
      title: `${t("retryPaymentRefund")} · ${shortId(refundId)}`,
      description: `${status} · ${codes.reason} · ${codes.reference}`,
      run: (actionId) => adminApi.retryPaymentRefund(refundId, codes, actionId),
    });
  }

  return (
    <div className="admin-reconciliation-view">
      <header className="admin-view-heading">
        <div>
          <p className="admin-kicker">STARS / LEDGER / RECONCILIATION</p>
          <h1>{t("reconciliationTitle")}</h1>
          <p>{t("reconciliationHelp")}</p>
        </div>
        <Status tone={canRefund ? "danger" : "pending"}>
          {canRefund ? t("writeAccess") : t("readOnly")}
        </Status>
      </header>

      <div className="admin-reconciliation-toolbar">
        <div className="admin-tabs" aria-label={t("issues")}>
          {filters.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={filter === item.id}
              className={filter === item.id ? "is-active" : ""}
              onClick={() => {
                setFilter(item.id);
                setOffset(0);
              }}
            >
              {t(item.label)}
            </button>
          ))}
        </div>
        <div className="admin-reconciliation-pagination" aria-label={t("pagination")}>
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset((value) => Math.max(0, value - 100))}
          >
            {t("previousPage")}
          </button>
          <span>{t("page")} {Math.floor(offset / 100) + 1}</span>
          <button
            type="button"
            disabled={
              !reconciliationQuery.data ||
              (reconciliationQuery.data.refunds.length < 100 &&
                reconciliationQuery.data.issues.length < 100)
            }
            onClick={() => setOffset((value) => value + 100)}
          >
            {t("nextPage")}
          </button>
        </div>
      </div>

      {canRefund ? (
        <form
          className="admin-payment-refund-request"
          aria-labelledby="payment-refund-request-title"
          onSubmit={(event) => {
            event.preventDefault();
            if (codesValid(codes) && isValidAdminUuid(orderId)) requestRefund();
          }}
        >
          <div className="admin-section-heading">
            <div><span>ACT</span><h2 id="payment-refund-request-title">{t("requestPaymentRefund")}</h2></div>
            <Status tone="danger">ADMIN</Status>
          </div>
          <SafeCodes value={codes} onChange={setCodes} t={t} idPrefix="payment-refund" />
          <label className="admin-field" htmlFor="payment-refund-order-id">
            <span>{t("paidOrderId")}</span>
            <input
              id="payment-refund-order-id"
              value={orderId}
              onChange={(event) => setOrderId(event.target.value)}
              placeholder="00000000-0000-4000-8000-000000000000"
              autoComplete="off"
              spellCheck={false}
            />
            <small>{t("paidOrderHelp")}</small>
          </label>
          <button
            type="submit"
            className="admin-button is-danger"
            disabled={!codesValid(codes) || !isValidAdminUuid(orderId)}
          >
            {t("requestPaymentRefund")}
          </button>
        </form>
      ) : null}

      {reconciliationQuery.isLoading ? <QueryNotice text={t("loading")} /> : null}
      {reconciliationQuery.isError ? (
        <div className="admin-reconciliation-error">
          <QueryNotice error text={errorMessage(reconciliationQuery.error, t("error"))} />
          <button type="button" className="admin-button is-muted" onClick={() => void reconciliationQuery.refetch()}>
            {t("retry")}
          </button>
        </div>
      ) : null}

      {reconciliationQuery.data ? (
        <>
          <section className="admin-reconciliation-run" aria-labelledby="latest-reconciliation-run">
            <div className="admin-section-heading">
              <div><span>RUN</span><h2 id="latest-reconciliation-run">{t("latestRun")}</h2></div>
              {reconciliationQuery.data.latest_run ? (
                <Status tone={statusTone(reconciliationQuery.data.latest_run.status)}>
                  {reconciliationLabel(reconciliationQuery.data.latest_run.status, t)}
                </Status>
              ) : null}
            </div>
            {reconciliationQuery.data.latest_run ? (
              <dl className="admin-reconciliation-facts">
                <div><dt>{t("fetched")}</dt><dd>{reconciliationQuery.data.latest_run.fetched_count}</dd></div>
                <div><dt>{t("issues")}</dt><dd>{reconciliationQuery.data.latest_run.issue_count}</dd></div>
                <div><dt>{t("lastError")}</dt><dd>{reconciliationQuery.data.latest_run.error_code ?? "—"}</dd></div>
                <div><dt>{t("lastSeen")}</dt><dd>{formatDate(reconciliationQuery.data.latest_run.finished_at ?? reconciliationQuery.data.latest_run.started_at, language)}</dd></div>
              </dl>
            ) : (
              <QueryNotice text={t("empty")} />
            )}
          </section>

          <section className="admin-reconciliation-group" aria-labelledby="payment-refunds-title">
            <div className="admin-section-heading">
              <div><span>01</span><h2 id="payment-refunds-title">{t("refunds")}</h2></div>
              <b>{reconciliationQuery.data.refunds.length}</b>
            </div>
            <div className="admin-refund-list">
              {reconciliationQuery.data.refunds.map((refund) => (
                <article key={refund.id}>
                  <header>
                    <div>
                      <Status tone={statusTone(refund.status)}>{reconciliationLabel(refund.status, t)}</Status>
                      <strong>{refund.stars_amount} XTR · {refund.credits_amount} cr</strong>
                    </div>
                    <code title={refund.id}>{shortId(refund.id)}</code>
                  </header>
                  <dl>
                    <div><dt>{t("order")}</dt><dd><code title={refund.order_id}>{shortId(refund.order_id)}</code></dd></div>
                    <div><dt>{t("attempts")}</dt><dd>{refund.attempt_count}</dd></div>
                    <div><dt>{t("lastError")}</dt><dd>{refund.last_error_code ?? "—"}</dd></div>
                    <div><dt>{t("firstSeen")}</dt><dd><time dateTime={refund.requested_at}>{formatDate(refund.requested_at, language)}</time></dd></div>
                    <div><dt>{t("lastSeen")}</dt><dd>{formatDate(refund.finished_at ?? refund.external_refunded_at, language)}</dd></div>
                    <div><dt>{t("ledgerTransaction")}</dt><dd>{refund.ledger_transaction_id ? <code title={refund.ledger_transaction_id}>{shortId(refund.ledger_transaction_id)}</code> : "—"}</dd></div>
                  </dl>
                  {canRefund && isPaymentRefundRetryable(refund.status) ? (
                    <button
                      type="button"
                      className="admin-text-action is-danger"
                      disabled={!codesValid(codes)}
                      onClick={() => requestRetry(refund.id, refund.status)}
                    >
                      {t("retryPaymentRefund")}
                    </button>
                  ) : null}
                </article>
              ))}
              {!reconciliationQuery.data.refunds.length ? <QueryNotice text={t("noRefunds")} /> : null}
            </div>
          </section>

          <section className="admin-reconciliation-group" aria-labelledby="reconciliation-issues-title">
            <div className="admin-section-heading">
              <div><span>02</span><h2 id="reconciliation-issues-title">{t("issues")}</h2></div>
              <b>{reconciliationQuery.data.issues.length}</b>
            </div>
            <div className="admin-issue-list">
              {reconciliationQuery.data.issues.map((issue) => (
                <article key={issue.id}>
                  <header>
                    <div>
                      <Status tone={issue.severity === "critical" ? "danger" : "pending"}>{reconciliationLabel(issue.severity, t)}</Status>
                      <strong>{issue.kind}</strong>
                    </div>
                    <Status tone={statusTone(issue.status)}>{reconciliationLabel(issue.status, t)}</Status>
                  </header>
                  <dl>
                    <div><dt>{t("order")}</dt><dd>{issue.order_id ? <code title={issue.order_id}>{shortId(issue.order_id)}</code> : "—"}</dd></div>
                    <div><dt>{t("refundId")}</dt><dd>{issue.refund_id ? <code title={issue.refund_id}>{shortId(issue.refund_id)}</code> : "—"}</dd></div>
                    <div><dt>{t("firstSeen")}</dt><dd><time dateTime={issue.first_seen_at}>{formatDate(issue.first_seen_at, language)}</time></dd></div>
                    <div><dt>{t("lastSeen")}</dt><dd><time dateTime={issue.last_seen_at}>{formatDate(issue.last_seen_at, language)}</time></dd></div>
                  </dl>
                  <div className="admin-safe-details">
                    <span>{t("details")}</span>
                    {safeIssueDetails(issue).length ? safeIssueDetails(issue).map(([key, value]) => (
                      <code key={key}>{key}={value}</code>
                    )) : <code>∅</code>}
                  </div>
                </article>
              ))}
              {!reconciliationQuery.data.issues.length ? <QueryNotice text={t("noIssues")} /> : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function ControlsView({
  operator,
  onAction,
  t,
}: {
  operator: AdminMe;
  onAction: RequestAction;
  t: (key: AdminMessageKey) => string;
}) {
  const controlsQuery = useQuery({ queryKey: ["admin", "controls"], queryFn: adminApi.controls });
  const [codes, setCodes] = useState<SafeActionInput>({ reason: "", reference: "" });
  const [templateOrders, setTemplateOrders] = useState<Record<string, string>>({});
  const canToggle = canRenderAdminAction(operator, "control.toggle");

  function toggle(
    kind: string,
    id: string,
    enabled: boolean,
    run: (actionId: string) => Promise<AuditEvent>,
  ) {
    onAction({
      title: `${enabled ? t("disable") : t("enable")} · ${id}`,
      description: `${kind} · ${codes.reason} · ${codes.reference}`,
      run,
    });
  }

  if (controlsQuery.isLoading) return <QueryNotice text={t("loading")} />;
  if (controlsQuery.isError) return <QueryNotice error text={errorMessage(controlsQuery.error, t("error"))} />;
  if (!controlsQuery.data) return null;

  return (
    <div className="admin-controls-view">
      <header className="admin-view-heading">
        <div><p className="admin-kicker">RUNTIME CONTROL PLANE</p><h1>{t("controls")}</h1></div>
        <Status tone={canToggle ? "danger" : "pending"}>{canToggle ? t("writeAccess") : t("readOnly")}</Status>
      </header>
      {canToggle ? (
        <section className="admin-control-reason">
          <SafeCodes value={codes} onChange={setCodes} t={t} idPrefix="control" />
          <p>{t("safeCodeHelp")}</p>
        </section>
      ) : null}
      <section className="admin-control-group">
        <div className="admin-section-heading"><div><span>01</span><h2>{t("providerHealth")}</h2></div><b>{controlsQuery.data.provider_health.length}</b></div>
        <div className="admin-control-list">
          {controlsQuery.data.provider_health.map((item) => {
            const tone = item.status === "healthy" || item.status === "ready"
              ? "ok"
              : item.status === "degraded" || item.status === "unconfigured"
                ? "danger"
                : "pending";
            return (
              <article key={`${item.provider}-${item.modality}`}>
                <div>
                  <strong>{item.provider} · {item.modality}</strong>
                  <span>
                    {item.recent_successes} {t("providerSuccesses")} · {item.recent_failures} {t("providerFailures")}
                    {item.canary ? ` · ${t("canary")}` : ""}
                  </span>
                </div>
                <Status tone={tone}>{t(item.status)}</Status>
              </article>
            );
          })}
        </div>
      </section>
      <section className="admin-control-group">
        <div className="admin-section-heading"><div><span>02</span><h2>{t("models")}</h2></div><b>{controlsQuery.data.models.length}</b></div>
        <div className="admin-control-list">
          {controlsQuery.data.models.map((model) => (
            <article key={model.slug}>
              <div><strong>{model.slug}</strong><span>{model.provider} · {model.modality} · {model.user_credit_price} кр.</span></div>
              <Status tone={model.enabled ? "ok" : "danger"}>{model.enabled ? t("enabled") : t("disabled")}</Status>
              {canToggle ? (
                <button type="button" disabled={!codesValid(codes)} onClick={() => toggle("MODEL", model.slug, model.enabled, (id) => adminApi.setModelEnabled(model.slug, !model.enabled, codes, id))}>
                  {model.enabled ? t("disable") : t("enable")}
                </button>
              ) : null}
            </article>
          ))}
        </div>
      </section>
      <section className="admin-control-group">
        <div className="admin-section-heading"><div><span>03</span><h2>{t("flags")}</h2></div><b>{controlsQuery.data.feature_flags.length}</b></div>
        <div className="admin-control-list is-compact">
          {controlsQuery.data.feature_flags.map((flag) => (
            <article key={flag.key}>
              <div><strong>{flag.key}</strong><span>FEATURE FLAG</span></div>
              <Status tone={flag.enabled ? "ok" : "danger"}>{flag.enabled ? t("enabled") : t("disabled")}</Status>
              {canToggle ? <button type="button" disabled={!codesValid(codes)} onClick={() => toggle("FLAG", flag.key, flag.enabled, (id) => adminApi.setFeatureFlagEnabled(flag.key, !flag.enabled, codes, id))}>{flag.enabled ? t("disable") : t("enable")}</button> : null}
            </article>
          ))}
        </div>
      </section>
      <section className="admin-control-group">
        <div className="admin-section-heading"><div><span>04</span><h2>{t("products")}</h2></div><b>{controlsQuery.data.payment_products.length}</b></div>
        <div className="admin-control-list">
          {controlsQuery.data.payment_products.map((product) => (
            <article key={product.slug}>
              <div><strong>{product.slug}</strong><span>{product.credits} кр. · {product.stars} XTR</span></div>
              <Status tone={product.enabled ? "ok" : "danger"}>{product.enabled ? t("enabled") : t("disabled")}</Status>
              {canToggle ? <button type="button" disabled={!codesValid(codes)} onClick={() => toggle("PRODUCT", product.slug, product.enabled, (id) => adminApi.setPaymentProductEnabled(product.slug, !product.enabled, codes, id))}>{product.enabled ? t("disable") : t("enable")}</button> : null}
            </article>
          ))}
        </div>
      </section>
      <section className="admin-control-group">
        <div className="admin-section-heading"><div><span>05</span><h2>{t("templates")}</h2></div><b>{controlsQuery.data.templates.length}</b></div>
        <div className="admin-control-list admin-template-list">
          {controlsQuery.data.templates.map((template) => {
            const orderValue = templateOrders[template.slug] ?? String(template.display_order);
            const parsedOrder = Number(orderValue);
            const orderValid = Number.isInteger(parsedOrder) && parsedOrder >= 0 && parsedOrder <= 10_000;
            const requestConfig = (enabled: boolean, displayOrder: number) =>
              onAction({
                title: `${t("templates")} · ${template.slug}`,
                description: `${template.kind} · ${codes.reason} · ${codes.reference}`,
                run: (actionId) =>
                  adminApi.setTemplateConfig(
                    template.slug,
                    enabled,
                    displayOrder,
                    codes,
                    actionId,
                  ),
              });
            return (
              <article key={template.slug}>
                <div>
                  <strong>{template.slug}</strong>
                  <span>{template.kind} · v{template.version}</span>
                </div>
                <Status tone={template.enabled ? "ok" : "danger"}>{template.enabled ? t("enabled") : t("disabled")}</Status>
                <div className={`admin-template-actions${canToggle ? "" : " is-readonly"}`}>
                  <label>
                    <span>{t("displayOrder")}</span>
                    {canToggle ? (
                      <input
                        type="number"
                        min="0"
                        max="10000"
                        step="1"
                        value={orderValue}
                        onChange={(event) =>
                          setTemplateOrders((current) => ({
                            ...current,
                            [template.slug]: event.target.value,
                          }))
                        }
                      />
                    ) : (
                      <output>{template.display_order}</output>
                    )}
                  </label>
                  {canToggle ? (
                    <>
                    <button
                      type="button"
                      disabled={!codesValid(codes) || !orderValid || parsedOrder === template.display_order}
                      onClick={() => requestConfig(template.enabled, parsedOrder)}
                    >
                      {t("save")}
                    </button>
                    <button
                      type="button"
                      disabled={!codesValid(codes) || !orderValid}
                      onClick={() => requestConfig(!template.enabled, parsedOrder)}
                    >
                      {template.enabled ? t("disable") : t("enable")}
                    </button>
                    </>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function Snapshot({ label, value }: { label: string; value: Record<string, string | number | boolean | null> }) {
  const entries = Object.entries(value);
  return (
    <div className="admin-snapshot">
      <span>{label}</span>
      {entries.length ? entries.map(([key, item]) => <code key={key}>{key}={String(item)}</code>) : <code>∅</code>}
    </div>
  );
}

function AuditView({ t }: { t: (key: AdminMessageKey) => string }) {
  const auditQuery = useQuery({ queryKey: ["admin", "audit"], queryFn: adminApi.audit });
  return (
    <div className="admin-audit-view">
      <header className="admin-view-heading">
        <div><p className="admin-kicker">APPEND ONLY / SAFE SNAPSHOTS</p><h1>{t("auditTitle")}</h1><p>{t("auditHelp")}</p></div>
        <span className="admin-audit-seal">SEALED</span>
      </header>
      {auditQuery.isLoading ? <QueryNotice text={t("loading")} /> : auditQuery.isError ? (
        <QueryNotice error text={errorMessage(auditQuery.error, t("error"))} />
      ) : (
        <ol className="admin-audit-list">
          {auditQuery.data?.map((event, index) => (
            <li key={event.id}>
              <span className="admin-audit-index">{String(index + 1).padStart(2, "0")}</span>
              <article>
                <header>
                  <div><Status tone="pending">{event.operator_role}</Status><strong>{event.action}</strong></div>
                  <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
                </header>
                <p><b>{event.object_type}</b> / <code title={event.object_id}>{shortId(event.object_id)}</code></p>
                <div className="admin-audit-reasons"><code>{event.reason}</code><code>{event.reference}</code></div>
                <div className="admin-snapshot-pair">
                  <Snapshot label={t("before")} value={event.before} />
                  <Snapshot label={t("after")} value={event.after} />
                </div>
                <footer>
                  <span>operator <code title={event.operator_user_id}>{shortId(event.operator_user_id)}</code></span>
                  <span>corr <code title={event.correlation_id}>{shortId(event.correlation_id)}</code></span>
                  <span>action <code title={event.action_id}>{shortId(event.action_id)}</code></span>
                </footer>
              </article>
            </li>
          ))}
          {!auditQuery.data?.length ? <QueryNotice text={t("empty")} /> : null}
        </ol>
      )}
    </div>
  );
}

function ModerationView({
  operator,
  onAction,
  t,
}: {
  operator: AdminMe;
  onAction: RequestAction;
  t: (key: AdminMessageKey) => string;
}) {
  const [status, setStatus] = useState<"open" | "reviewed">("open");
  const [codes, setCodes] = useState<SafeActionInput>({ reason: "", reference: "" });
  const queueQuery = useQuery({
    queryKey: ["admin", "moderation", status],
    queryFn: () => adminApi.moderation(status),
  });
  const canReview = canRenderAdminAction(operator, "moderation.review");
  const outcomes: Array<{
    id: ModerationReviewOutcome;
    label: AdminMessageKey;
  }> = [
    { id: "confirmed_violation", label: "confirmedViolation" },
    { id: "false_positive", label: "falsePositive" },
    { id: "needs_escalation", label: "needsEscalation" },
  ];

  function requestReview(decision: AdminModerationDecision, outcome: ModerationReviewOutcome) {
    onAction({
      title: `${t(outcomes.find((item) => item.id === outcome)?.label ?? "review")} · ${shortId(decision.id)}`,
      description: `${decision.outcome} · ${codes.reason} · ${codes.reference}`,
      run: (actionId) => adminApi.reviewModeration(decision.id, outcome, codes, actionId),
    });
  }

  return (
    <div className="admin-moderation-view">
      <header className="admin-view-heading">
        <div>
          <p className="admin-kicker">METADATA ONLY / NO RAW INPUT</p>
          <h1>{t("moderationTitle")}</h1>
          <p>{t("moderationHelp")}</p>
        </div>
        <Status tone={canReview ? "danger" : "pending"}>
          {canReview ? t("writeAccess") : t("readOnly")}
        </Status>
      </header>
      <div className="admin-moderation-toolbar">
        <div className="admin-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={status === "open"} className={status === "open" ? "is-active" : ""} onClick={() => setStatus("open")}>{t("openQueue")}</button>
          <button type="button" role="tab" aria-selected={status === "reviewed"} className={status === "reviewed" ? "is-active" : ""} onClick={() => setStatus("reviewed")}>{t("reviewedQueue")}</button>
        </div>
        <AdminCapabilityGate operator={operator} action="moderation.review">
          <div className="admin-moderation-reason">
            <SafeCodes value={codes} onChange={setCodes} t={t} idPrefix="moderation-review" />
            <p>{t("safeCodeHelp")}</p>
          </div>
        </AdminCapabilityGate>
      </div>
      {queueQuery.isLoading ? <QueryNotice text={t("loading")} /> : queueQuery.isError ? (
        <QueryNotice error text={errorMessage(queueQuery.error, t("error"))} />
      ) : (
        <div className="admin-moderation-list">
          {queueQuery.data?.map((decision) => (
            <article key={decision.id}>
              <header>
                <div>
                  <Status tone={statusTone(decision.outcome)}>{decision.outcome}</Status>
                  <strong>{decision.context}</strong>
                  <code title={decision.id}>{shortId(decision.id)}</code>
                </div>
                <time dateTime={decision.created_at}>{formatDate(decision.created_at)}</time>
              </header>
              <dl>
                <div><dt>Reason codes</dt><dd>{decision.reason_codes.length ? decision.reason_codes.join(" · ") : "—"}</dd></div>
                <div><dt>Policy</dt><dd>{decision.policy_version}</dd></div>
                <div><dt>Provider</dt><dd>{decision.provider}{decision.provider_model ? ` / ${decision.provider_model}` : ""}</dd></div>
                <div><dt>Input hash</dt><dd><code title={decision.input_hash}>{shortId(decision.input_hash)}</code></dd></div>
                <div><dt>Assets</dt><dd>{decision.asset_ids.length}</dd></div>
                <div><dt>User</dt><dd><code title={decision.user_id}>{shortId(decision.user_id)}</code></dd></div>
                <div><dt>Error</dt><dd>{decision.error_code ?? "—"}</dd></div>
                <div><dt>Review</dt><dd>{decision.review_outcome ?? decision.review_status}</dd></div>
              </dl>
              {status === "open" ? (
                <AdminCapabilityGate operator={operator} action="moderation.review">
                  <footer>
                    {outcomes.map((outcome) => (
                      <button
                        key={outcome.id}
                        type="button"
                        disabled={!codesValid(codes)}
                        onClick={() => requestReview(decision, outcome.id)}
                      >
                        {t(outcome.label)}
                      </button>
                    ))}
                  </footer>
                </AdminCapabilityGate>
              ) : null}
            </article>
          ))}
          {!queueQuery.data?.length ? <QueryNotice text={t("empty")} /> : null}
        </div>
      )}
    </div>
  );
}

function ReferralView({
  t,
  language,
}: {
  t: (key: AdminMessageKey) => string;
  language: Language;
}) {
  const referralsQuery = useQuery({
    queryKey: ["admin", "referrals"],
    queryFn: adminApi.referrals,
  });
  if (referralsQuery.isLoading) return <QueryNotice text={t("loading")} />;
  if (referralsQuery.isError) {
    return <QueryNotice error text={errorMessage(referralsQuery.error, t("error"))} />;
  }
  return (
    <div className="admin-referrals-view">
      <header className="admin-page-heading">
        <div>
          <p className="admin-kicker">REFERRAL / LEDGER</p>
          <h1>{t("referralsTitle")}</h1>
          <p>{t("referralsHelp")}</p>
        </div>
      </header>
      <section className="admin-control-group">
        <div className="admin-section-heading">
          <div><span>01</span><h2>{t("reward")}</h2></div>
          <b>{referralsQuery.data?.length ?? 0}</b>
        </div>
        <div className="admin-control-list">
          {referralsQuery.data?.map((reward: AdminReferralReward) => (
            <article key={reward.id} className="admin-control-row">
              <div>
                <strong>{shortId(reward.id)}</strong>
                <small>
                  {t("inviter")}: {shortId(reward.inviter_user_id)} · {t("invited")}: {shortId(reward.invited_user_id)}
                </small>
                <small>
                  {reward.inviter_bonus_credits} + {reward.invitee_bonus_credits} credits · {formatDate(reward.credited_at ?? reward.eligible_at ?? reward.created_at, language)}
                </small>
                {reward.review_reason ? <code>{reward.review_reason}</code> : null}
              </div>
              <Status tone={statusTone(reward.status)}>{reconciliationLabel(reward.status, t)}</Status>
            </article>
          ))}
          {!referralsQuery.data?.length ? <QueryNotice text={t("empty")} /> : null}
        </div>
      </section>
    </div>
  );
}

export function AdminPage() {
  const { language } = useI18n();
  const t = (key: AdminMessageKey) => adminMessage(language, key);
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [section, setSection] = useState<AdminSection>("users");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [outcome, setOutcome] = useState<AuditEvent | null>(null);
  const token = getToken();
  const operatorQuery = useQuery({
    queryKey: ["admin", "me"],
    queryFn: adminApi.me,
    enabled: Boolean(token),
    retry: false,
  });
  const actionMutation = useMutation({
    mutationFn: (action: PendingAction) => action.run(action.actionId),
    onSuccess: async (audit) => {
      setOutcome(audit);
      setPending(null);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  function signInAgain() {
    setToken(null);
    void navigate("/boot", { replace: true, state: { returnTo: "/admin" } });
  }

  function requestAction(action: Omit<PendingAction, "actionId">) {
    actionMutation.reset();
    setOutcome(null);
    setPending({ ...action, actionId: crypto.randomUUID() });
  }

  if (!token) {
    return <Navigate to="/boot" replace state={{ returnTo: currentAppPath(location) }} />;
  }
  if (operatorQuery.isLoading) return <AdminState code="AUTH" title={t("loading")} body={t("unavailableBody")} />;
  if (operatorQuery.error instanceof ApiError && operatorQuery.error.status === 401) {
    return <AdminState code="401" title={t("expiredTitle")} body={t("expiredBody")} action={<button className="admin-button" type="button" onClick={signInAgain}>{t("signIn")}</button>} />;
  }
  if (operatorQuery.error instanceof ApiError && [403, 404].includes(operatorQuery.error.status)) {
    return <AdminState code="403" title={t("forbiddenTitle")} body={t("forbiddenBody")} action={<Link className="admin-button is-muted" to="/">Mini App</Link>} />;
  }
  if (operatorQuery.isError || !operatorQuery.data) {
    return <AdminState code="ERR" title={t("unavailableTitle")} body={errorMessage(operatorQuery.error, t("unavailableBody"))} action={<button className="admin-button" type="button" onClick={() => void operatorQuery.refetch()}>{t("retry")}</button>} />;
  }

  return (
    <div className="admin-shell">
      <AdminHeader operator={operatorQuery.data} t={t} />
      <div className="admin-shell-grid">
        <AdminNav section={section} onChange={setSection} t={t} />
        <main className="admin-main">
          {outcome ? (
            <div className="admin-outcome" role="status">
              <span aria-hidden>✓</span><p><strong>{t("result")}</strong><code>{outcome.action} / {shortId(outcome.action_id)}</code></p>
              <button type="button" onClick={() => setOutcome(null)} aria-label="Закрыть">×</button>
            </div>
          ) : null}
          {section === "users" ? <UserWorkspace operator={operatorQuery.data} onAction={requestAction} t={t} /> : null}
          {section === "controls" ? <ControlsView operator={operatorQuery.data} onAction={requestAction} t={t} /> : null}
          {section === "moderation" ? <ModerationView operator={operatorQuery.data} onAction={requestAction} t={t} /> : null}
          {section === "reconciliation" ? <PaymentReconciliationView operator={operatorQuery.data} onAction={requestAction} t={t} language={language} /> : null}
          {section === "referrals" ? <ReferralView t={t} language={language} /> : null}
          {section === "audit" ? <AuditView t={t} /> : null}
        </main>
      </div>
      {pending ? (
        <div className="admin-confirm-layer">
          <ConfirmDialog
            action={pending}
            busy={actionMutation.isPending}
            error={actionMutation.isError ? errorMessage(actionMutation.error, t("error")) : null}
            onConfirm={() => actionMutation.mutate(pending)}
            onCancel={() => { actionMutation.reset(); setPending(null); }}
            t={t}
          />
        </div>
      ) : null}
    </div>
  );
}
