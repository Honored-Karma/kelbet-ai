import { createElement, Fragment, type ReactNode } from "react";
import { canRenderAdminAction } from "./permissions.ts";
import type { AdminMe } from "./types.ts";

type AdminAction = Parameters<typeof canRenderAdminAction>[1];

export function AdminCapabilityGate({
  operator,
  action,
  children,
}: {
  operator: AdminMe;
  action: AdminAction;
  children: ReactNode;
}) {
  if (!canRenderAdminAction(operator, action)) return null;
  return createElement(Fragment, null, children);
}
