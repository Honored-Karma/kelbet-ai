import { useEffect, useRef } from "react";
import { useI18n } from "../i18n/runtime";
import { Icon } from "./Icon";

type RecoveryMode = "quote" | "expired" | "submission";

export function GenerationRecovery({
  mode,
  onAction,
}: {
  mode: RecoveryMode;
  onAction: () => void;
}) {
  const { tx } = useI18n();
  const actionRef = useRef<HTMLButtonElement>(null);
  const isRefresh = mode === "quote" || mode === "expired";

  useEffect(() => {
    actionRef.current?.focus();
  }, [mode]);

  const title = tx(
    mode === "quote"
      ? "recovery.quoteTitle"
      : mode === "expired"
        ? "recovery.expiredTitle"
        : "recovery.submissionTitle",
  );
  const body = tx(
    mode === "quote"
      ? "recovery.quoteBody"
      : mode === "expired"
        ? "recovery.expiredBody"
        : "recovery.submissionBody",
  );

  return (
    <section className="generation-recovery" role="alert" aria-labelledby="generation-recovery-title">
      <span className="generation-recovery-mark" aria-hidden>
        <Icon name="repeat" />
      </span>
      <div>
        <strong id="generation-recovery-title">{title}</strong>
        <p>{body}</p>
      </div>
      <button ref={actionRef} type="button" onClick={onAction}>
        <Icon name="repeat" />
        {tx(isRefresh ? "recovery.refreshQuote" : "recovery.retryRequest")}
      </button>
    </section>
  );
}
