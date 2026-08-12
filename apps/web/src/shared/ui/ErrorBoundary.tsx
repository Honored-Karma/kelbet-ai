import { Component, type ErrorInfo, type ReactNode } from "react";

type Labels = {
  title: string;
  body: string;
  action: string;
};

type Props = {
  labels: Labels;
  children: ReactNode;
};

type State = {
  failed: boolean;
};

/**
 * Последний рубеж перед белым экраном.
 *
 * Все двенадцать страниц загружаются через React.lazy, и любая ошибка рендера
 * внутри них доходила до корня React, размонтировала дерево и оставляла
 * пользователю пустой документ — без текста, без кнопки, без объяснения. В
 * Telegram WebView это выглядит как сломанное приложение, а не как сбой одного
 * экрана.
 *
 * Границы намеренно нет вокруг каждой страницы по отдельности: состояние
 * приложения после необработанной ошибки рендера неизвестно, и предлагать
 * «вернуться назад» внутри того же дерева значит предлагать пользователю
 * гадать. Перезагрузка — единственное честное действие, которое мы можем
 * обещать.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Sentry подключается отдельно и по умолчанию выключен; до тех пор консоль —
    // единственное место, где след ошибки вообще остаётся.
    console.error("[KELBET] необработанная ошибка рендера", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) {
      return this.props.children;
    }
    const { title, body, action } = this.props.labels;
    return (
      <div className="app-crash" role="alert">
        <div className="app-crash-mark" aria-hidden>
          K
        </div>
        <h1>{title}</h1>
        <p>{body}</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>
          {action}
        </button>
      </div>
    );
  }
}
