import type { ReactNode } from "react";

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel state-card rise">
      <h2>{title}</h2>
      {body ? <p className="muted">{body}</p> : null}
      {action}
    </div>
  );
}
