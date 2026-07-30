type ApiBaseUrlOptions = {
  production: boolean;
};

export type ApiBaseUrlValidation =
  | { ok: true; url: string }
  | { ok: false; reason: string };

const PLACEHOLDER_MARKERS = [
  "replace",
  "your-api",
  "your_api",
  "ваш_api",
  "ваш-api",
  "ваш api",
  "example.",
  "<",
  ">",
];

export function validateApiBaseUrl(
  value: string | undefined,
  options: ApiBaseUrlOptions,
): ApiBaseUrlValidation {
  const raw = (value ?? "").trim().replace(/\/+$/, "");
  if (!raw) {
    return { ok: false, reason: "the URL is empty" };
  }

  const lowered = raw.toLowerCase();
  if (PLACEHOLDER_MARKERS.some((marker) => lowered.includes(marker))) {
    return { ok: false, reason: "the URL still contains a placeholder" };
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return { ok: false, reason: "the value is not an absolute URL" };
  }

  if (parsed.username || parsed.password) {
    return { ok: false, reason: "credentials must not be embedded in the URL" };
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    return { ok: false, reason: "use the API origin without a path, query, or hash" };
  }

  const isLocal = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  if (options.production && isLocal) {
    return { ok: false, reason: "localhost cannot be used in a production build" };
  }
  if (parsed.protocol !== "https:" && !isLocal) {
    return { ok: false, reason: "the remote API must use HTTPS" };
  }

  return { ok: true, url: raw };
}
