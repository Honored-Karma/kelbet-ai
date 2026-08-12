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

/**
 * Тактильная отдача. Всё опционально по цепочке: HapticFeedback появился не во
 * всех клиентах Telegram, а на десктопе метода может не быть вовсе. Отсутствие
 * отдачи — не ошибка и не должно ронять действие, которое её вызвало.
 */
export function hapticImpact(style: "light" | "medium" | "heavy" = "medium"): void {
  getTelegramWebApp()?.HapticFeedback?.impactOccurred?.(style);
}

export function hapticNotify(type: "success" | "error" | "warning"): void {
  getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.(type);
}

/**
 * Нативная кнопка «назад» в шапке Telegram.
 *
 * Возвращает функцию отписки. Обработчик обязательно снимается через offClick:
 * Telegram держит подписки на стороне клиента, и незакрытая подписка продолжает
 * навигировать после того, как экран уже размонтирован.
 */
export function showBackButton(onClick: () => void): () => void {
  const webApp = getTelegramWebApp();
  const backButton = webApp?.BackButton;
  if (!backButton) {
    return () => {};
  }
  backButton.onClick(onClick);
  backButton.show();
  return () => {
    backButton.offClick(onClick);
    backButton.hide();
  };
}

export function hideBackButton(): void {
  getTelegramWebApp()?.BackButton?.hide();
}
