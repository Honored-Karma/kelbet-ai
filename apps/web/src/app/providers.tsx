import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { I18nProvider } from "../shared/i18n/context";
import { useI18n } from "../shared/i18n/runtime";
import { ErrorBoundary } from "../shared/ui/ErrorBoundary";
import { AppRouter } from "./router";
import { SessionGuard } from "./SessionGuard";

focusManager.setEventListener((handleFocus) => {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  const onVisibility = () => {
    handleFocus(document.visibilityState === "visible");
  };
  const onOnline = () => handleFocus(true);
  window.addEventListener("visibilitychange", onVisibility, false);
  window.addEventListener("online", onOnline, false);
  return () => {
    window.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("online", onOnline);
  };
});

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: 1,
        refetchOnWindowFocus: true,
      },
    },
  });
}

/**
 * Живёт внутри I18nProvider, потому что подписи границы ошибок должны быть на
 * языке пользователя, и внутри роутера, потому что SessionGuard навигирует.
 */
function Shell({ children }: { children?: ReactNode }) {
  const { tx } = useI18n();
  return (
    <ErrorBoundary
      labels={{
        title: tx("crash.title"),
        body: tx("crash.body"),
        action: tx("crash.action"),
      }}
    >
      <SessionGuard>{children ?? <AppRouter />}</SessionGuard>
    </ErrorBoundary>
  );
}

export function AppProviders({ children }: { children?: ReactNode }) {
  const [client] = useState(() => makeClient());
  useEffect(() => {
    document.documentElement.dataset.apiMode = import.meta.env.VITE_API_MODE || "mock";
  }, []);

  return (
    <QueryClientProvider client={client}>
      <I18nProvider>
        <BrowserRouter>
          <Shell>{children}</Shell>
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  );
}
