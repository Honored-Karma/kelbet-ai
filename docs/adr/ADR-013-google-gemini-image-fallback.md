# ADR-013: Google Gemini as the independent image fallback

**Status:** Accepted  
**Date:** 2026-08-01

## Context

Production image generation and editing currently depend on Runway. A second,
independent route is needed for classified transient failures. Google Imagen was
the initial candidate, but the current official Gemini API documentation marks
Imagen models as deprecated and schedules their shutdown for 17 August 2026.
Google's current stable native image model is `gemini-3.1-flash-image`.

The documented model supports image generation, image input and image editing,
including 512, 1K, 2K and 4K outputs. The documentation does not define a
deterministic pixel-preserving upscale operation equivalent to KELBET's Magnific
SKU.

## Decision

- Implement `GoogleGeminiImageProvider` behind the existing
  `GenerationProvider` protocol and provider factory.
- Use `POST /v1beta/interactions` with the stable model ID
  `gemini-3.1-flash-image`.
- Support fallback for `image` and `image_edit`; keep `upscale` explicitly
  unsupported and without a fallback route.
- Generalize the existing video fallback engine. Do not create a second routing
  mechanism.
- Store an immutable routing/cost snapshot at quote and job creation. Runtime
  kill switches remain live so an operator can stop a route.
- Permit fallback only for timeout, rate limit, upstream 5xx/unavailable or a
  transport failure without a reliable permanent status.
- Never fall back after moderation rejection, invalid input, unsupported
  capability, missing credentials or permanent account/authentication errors.
- Require both `google_image` and `image_fallback` feature flags. Their existing
  `telegram_ids` payload is the canary allowlist. Both flags are off by default.
- Enforce the provider cost ceiling from the quote-time routing snapshot. The
  user's credit price is never recalculated after the quote.
- Persist typed safe diagnostics only. Prompts, input images and raw provider
  responses never enter logs, usage metadata, metrics or audit records.

## Coverage matrix

| KELBET operation | Gemini coverage | Fallback |
|---|---|---|
| image generation | Officially supported | Yes, canary/flags/cost/transient gates |
| image edit | Officially supported with image input | Yes, same gates |
| deterministic upscale | No equivalent documented | No |

Resolution aliases are bounded: `720p`, `1080p` and `1k` map to Google `1K`;
`2k` and `3k` map to `2K`; `4k` maps to `4K`. Unsupported ratios or sizes stop
without a fallback attempt.

## Consequences

Runway remains the primary route and existing user-facing SKUs do not change.
Each attempt and final provider route is visible in `generation_attempts`,
`provider_usage` and the admin provider-health panel. A transient failure can
consume provider cost on more than one route, so rollout requires billing alerts
and the catalog ceiling. Rollback is immediate by disabling `image_fallback` or
`google_image`; already completed wallet capture/release operations are not
replayed.

Official references verified on 1 August 2026:

- <https://ai.google.dev/gemini-api/docs/image-generation>
- <https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image>
- <https://ai.google.dev/gemini-api/docs/pricing>
- <https://ai.google.dev/gemini-api/docs/available-regions>
- <https://ai.google.dev/gemini-api/docs/deprecations>
