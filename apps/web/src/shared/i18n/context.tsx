import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Language } from "../api/types";
import { t, type MessageKey } from "./messages";
import { I18nContext } from "./runtime";

const LANGUAGE_STORAGE_KEY = "kelbet.language";

function restoredLanguage(fallback: Language): Language {
  if (typeof localStorage === "undefined") return fallback;
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored === "ru" || stored === "kk" ? stored : fallback;
  } catch {
    return fallback;
  }
}

export function I18nProvider({
  initialLanguage = "ru",
  children,
}: {
  initialLanguage?: Language;
  children: ReactNode;
}) {
  const [language, setLanguage] = useState<Language>(() => restoredLanguage(initialLanguage));
  useLayoutEffect(() => {
    document.documentElement.lang = language;
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // Storage may be unavailable in restricted webviews; in-memory locale still works.
    }
  }, [language]);
  const tx = useCallback((key: MessageKey) => t(language, key), [language]);
  const value = useMemo(
    () => ({ language, setLanguage, tx }),
    [language, tx],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
