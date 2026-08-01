import { useState } from "react";
import { Link } from "react-router-dom";
import { SUPPORT_COMMAND, supportCopy } from "../features/support/contract";
import { useI18n } from "../shared/i18n/runtime";
import { getTelegramWebApp } from "../shared/telegram/webapp";

type CopyState = "idle" | "copied" | "failed";

export function SupportPage() {
  const { language } = useI18n();
  const text = supportCopy[language];
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const telegramWebApp = getTelegramWebApp();

  async function copyCommand() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard_unavailable");
      await navigator.clipboard.writeText(SUPPORT_COMMAND);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <section className="support-page rise" aria-labelledby="support-title">
      <header className="support-masthead">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 id="support-title">{text.title}</h1>
        <p>{text.body}</p>
      </header>

      <ol className="support-steps">
        <li>
          <span aria-hidden>01</span>
          <p>{text.stepChat}</p>
        </li>
        <li>
          <span aria-hidden>02</span>
          <p>{text.stepCommand}</p>
        </li>
      </ol>

      <section className="support-command" aria-labelledby="support-command-title">
        <div>
          <span id="support-command-title">BOT COMMAND</span>
          <code tabIndex={0}>{SUPPORT_COMMAND}</code>
        </div>
        <button type="button" onClick={() => void copyCommand()}>
          {copyState === "copied" ? text.copied : text.copy}
        </button>
        <p className={copyState === "failed" ? "is-error" : ""} aria-live="polite">
          {copyState === "copied"
            ? text.copied
            : copyState === "failed"
              ? text.copyFailed
              : ""}
        </p>
      </section>

      <div className="support-actions">
        {telegramWebApp ? (
          <button type="button" className="support-chat-button" onClick={() => telegramWebApp.close()}>
            {text.returnToChat}
          </button>
        ) : (
          <p>{text.browserNote}</p>
        )}
        <Link to="/profile">← {text.back}</Link>
      </div>
    </section>
  );
}
