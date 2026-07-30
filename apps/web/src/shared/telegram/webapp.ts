export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function bootTelegram(): TelegramWebApp | null {
  const webApp = getTelegramWebApp();
  if (!webApp) {
    return null;
  }
  webApp.ready();
  webApp.expand();
  applyTelegramTheme(webApp);
  return webApp;
}

export function applyTelegramTheme(webApp: TelegramWebApp): void {
  const root = document.documentElement;
  const params = webApp.themeParams;
  for (const [key, value] of Object.entries(params)) {
    if (!value) continue;
    const cssKey = `--tg-theme-${key.replace(/_/g, "-")}`;
    root.style.setProperty(cssKey, value.startsWith("#") ? value : `#${value}`);
  }
  webApp.setHeaderColor?.(params.bg_color ? `#${params.bg_color.replace("#", "")}` : "#0b1c1a");
  webApp.setBackgroundColor?.(
    params.bg_color ? `#${params.bg_color.replace("#", "")}` : "#0b1c1a",
  );
}

export function getInitData(): string {
  return getTelegramWebApp()?.initData ?? "";
}
