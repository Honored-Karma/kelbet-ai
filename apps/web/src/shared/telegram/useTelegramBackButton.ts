import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { hideBackButton, showBackButton } from "./webapp";

/**
 * Маршруты нижней навигации. На них нативная кнопка «назад» не показывается:
 * это корневые вкладки, и уводить с них «назад» некуда — Telegram в таком случае
 * закрыл бы мини-приложение, чего пользователь не просил.
 */
const ROOT_ROUTES = new Set(["/", "/history", "/create", "/plans", "/profile"]);

/**
 * Показывает нативную кнопку «назад» на вложенных экранах.
 *
 * До этого из Telegram SDK не использовалась ни одна кнопка: навигация шла
 * только по внутренним ссылкам, и с экрана результата или тарифов вернуться
 * можно было лишь через нижнюю навигацию. В Telegram место для «назад» уже
 * занято шапкой клиента, и её пустота на вложенном экране читается как
 * недоделка.
 */
export function useTelegramBackButton(): void {
  const location = useLocation();
  const navigate = useNavigate();
  const isRoot = ROOT_ROUTES.has(location.pathname);
  // Ключ "default" означает первую запись в истории: мини-приложение открыли
  // прямо на этом экране по ссылке, и шага назад не существует.
  const isFirstEntry = location.key === "default";

  useEffect(() => {
    if (isRoot) {
      hideBackButton();
      return;
    }
    return showBackButton(() => {
      if (isFirstEntry) {
        navigate("/", { replace: true });
        return;
      }
      navigate(-1);
    });
  }, [isRoot, isFirstEntry, navigate]);
}
