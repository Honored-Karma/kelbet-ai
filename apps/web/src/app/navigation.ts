type RouteLocation = {
  pathname: string;
  search: string;
  hash: string;
};

type BootLocationState = {
  returnTo?: unknown;
};

const STATIC_APP_PATHS = new Set([
  "/",
  "/create",
  "/video",
  "/trends",
  "/history",
  "/plans",
  "/profile",
  "/support",
  "/invite",
  "/admin",
]);

const GENERATION_PATH = /^\/generations\/[0-9a-f-]+$/i;

export function currentAppPath(location: RouteLocation): string {
  return `${location.pathname}${location.search}${location.hash}`;
}

export function resolveBootReturnTo(state: unknown): string {
  if (!state || typeof state !== "object") return "/";

  const candidate = (state as BootLocationState).returnTo;
  if (typeof candidate !== "string" || !candidate.startsWith("/")) return "/";

  let parsed: URL;
  try {
    parsed = new URL(candidate, "https://kelbet.local");
  } catch {
    return "/";
  }
  if (parsed.origin !== "https://kelbet.local") return "/";
  if (!STATIC_APP_PATHS.has(parsed.pathname) && !GENERATION_PATH.test(parsed.pathname)) {
    return "/";
  }
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}
