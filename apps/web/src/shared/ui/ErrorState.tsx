export function ErrorState({
  title,
  body,
  onRetry,
  retryLabel,
}: {
  title: string;
  body?: string;
  onRetry?: () => void;
  retryLabel: string;
}) {
  return (
    <div className="panel state-card rise" role="alert">
      <h2>{title}</h2>
      {body ? <p className="muted">{body}</p> : null}
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
