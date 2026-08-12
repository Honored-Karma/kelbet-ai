import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { UNAUTHORIZED_EVENT } from "../shared/api/client";

/**
 * Слушает признание сессии недействительной и уводит на переавторизацию.
 *
 * Токен живёт в sessionStorage и имеет серверный TTL. По его истечении каждый
 * запрос отвечал 401, транспортный слой честно превращал это в ApiError, и
 * пользователь получал экран ошибки с кнопкой «повторить», которая приводила к
 * той же ошибке. Выхода из этого состояния в приложении не было.
 *
 * Кеш очищается до перехода: ответы, полученные под прежней сессией, больше не
 * должны показываться, даже на долю секунды.
 */
export function SessionGuard({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    const onUnauthorized = () => {
      queryClient.clear();
      navigate("/boot", { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    };
  }, [navigate, queryClient]);

  return children;
}
