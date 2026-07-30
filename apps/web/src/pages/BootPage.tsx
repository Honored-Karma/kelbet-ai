import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import contactSheet from "../assets/kelbet-contact-sheet.webp";
import { api, getApiMode, getToken, setToken } from "../shared/api/client";
import { useI18n } from "../shared/i18n/runtime";
import { bootTelegram, getInitData } from "../shared/telegram/webapp";
import { ErrorState } from "../shared/ui/ErrorState";

export function BootPage() {
  const navigate = useNavigate();
  const { tx, setLanguage } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const started = useRef(false);

  async function authenticate() {
    setBusy(true);
    setError(null);
    try {
      bootTelegram();
      if (!getToken()) {
        const initData = getInitData();
        if (getApiMode() === "live" && !initData) {
          throw new Error("missing_init_data");
        }
        const auth = await api.authTelegram(initData || "mock");
        setToken(auth.access_token);
        setLanguage(auth.user.language);
      }
      void navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "auth_failed");
      setBusy(false);
    }
  }

  useEffect(() => {
    if (started.current) {
      return;
    }
    started.current = true;
    void authenticate();
    // intentionally once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="app-main">
        <ErrorState
          title={tx("auth.failed")}
          body={error}
          onRetry={() => {
            started.current = false;
            void authenticate();
          }}
          retryLabel={tx("common.retry")}
        />
      </div>
    );
  }

  return (
    <div className="boot-page rise">
      <div className="boot-art" aria-hidden>
        <img src={contactSheet} alt="" />
        <span>K / 01—04</span>
      </div>
      <div className="boot-lockup">
        <span className="boot-mark" aria-hidden>K</span>
        <div>
          <div className="brand">KELBET</div>
          <p>{busy ? tx("auth.booting") : tx("common.loading")}</p>
        </div>
      </div>
      <div className="boot-progress" aria-hidden><span /></div>
    </div>
  );
}
