import type { AdminMe } from "./types";

const WRITE_CAPABILITIES = new Set(["write", "admin:write", "admin.write"]);

export function hasAdminWriteCapability(operator: AdminMe): boolean {
  const capabilities = operator.capabilities;
  if (Array.isArray(capabilities)) {
    return capabilities.some((capability) => WRITE_CAPABILITIES.has(capability));
  }
  const capabilityMap = capabilities as Record<string, boolean>;
  return [...WRITE_CAPABILITIES].some((capability) => capabilityMap[capability] === true);
}

export function canRenderAdminAction(
  operator: AdminMe,
  action:
    | "wallet.grant"
    | "user.block"
    | "generation.refund"
    | "payment.refund"
    | "control.toggle"
    | "moderation.review",
): boolean {
  if (!hasAdminWriteCapability(operator)) return false;
  const capabilities = operator.capabilities;
  if (Array.isArray(capabilities)) {
    const scoped = `admin:${action}`;
    const usesScopedCapabilities = capabilities.some((item) => item.startsWith("admin:"));
    return !usesScopedCapabilities || capabilities.includes(scoped) || capabilities.includes("admin:write");
  }
  const capabilityMap = capabilities as Record<string, boolean>;
  const scoped = `admin:${action}`;
  const usesScopedCapabilities = Object.keys(capabilityMap).some((item) => item.startsWith("admin:"));
  return !usesScopedCapabilities || capabilityMap[scoped] === true || capabilityMap["admin:write"] === true;
}
