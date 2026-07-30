import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { I18nProvider } from "../shared/i18n/context";
import { AppRouter } from "./router";

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

export function AppProviders({ children }: { children?: ReactNode }) {
  const [client] = useState(() => makeClient());
  useEffect(() => {
    document.documentElement.dataset.apiMode = import.meta.env.VITE_API_MODE || "mock";
  }, []);

  return (
    <QueryClientProvider client={client}>
      <I18nProvider>
        <BrowserRouter>{children ?? <AppRouter />}</BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  );
}
