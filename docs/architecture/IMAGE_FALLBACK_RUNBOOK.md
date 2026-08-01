# Image provider fallback runbook

Status: technically implemented, production rollout not confirmed  
Updated: 1 August 2026

## Safety contract

Runway is primary. Google Gemini `gemini-3.1-flash-image` is an independent
fallback for image generation and edit only. Upscale never switches provider.

The route requires all of the following:

1. the original job contains a quote-time fallback and cost-ceiling snapshot;
2. the primary failure is classified as transient;
3. `GOOGLE_API_KEY` is configured in API and image worker environments;
4. `google_image` is enabled;
5. `image_fallback` is enabled;
6. if either flag has `payload.telegram_ids`, the user is in that allowlist;
7. expected Google cost does not exceed the immutable ceiling;
8. no prior provider switch has already occurred.

Missing key, moderation rejection, 4xx validation, unsupported capability,
account/auth errors, unknown resolution and upscale all stop without fallback.

## Canary

Keep both flags disabled after deployment. In `/admin`:

1. verify provider health shows Google image as `unconfigured` or `disabled`
   until the key and flags exist;
2. configure the API key without placing it in source control;
3. set both flags' payload to the same small `telegram_ids` allowlist directly
   through the approved database/configuration procedure;
4. enable `google_image`, then `image_fallback` with audited admin actions;
5. force a safe transient primary failure in staging;
6. verify two attempts, final route `google`, one wallet capture, unchanged user
   credit price and no prompt/image/raw response in logs;
7. compare `provider.route`, latency and cost metrics with the provider invoice;
8. expand the allowlist only after the sample meets quality and cost thresholds.

The admin UI intentionally shows only whether a flag is in canary mode, not the
Telegram IDs in its payload.

## Rollback

Disable `image_fallback` first. If Google itself is unhealthy, also disable
`google_image`. Do not disable or edit completed jobs. New transient Runway
failures will release their reservation instead of switching. Existing jobs
already running at Google complete against their stored route; terminal replay
remains idempotent.

Use `runway_media` only as the primary catalog kill switch for new quotes. It is
not a substitute for the fallback flags.

## Incident checks

- High fallback rate: inspect the primary failure classification and Runway
  status; never widen the retry classifier during an incident.
- High Google failure rate: disable `image_fallback`, then inspect bounded HTTP
  status/error codes. Do not log response bodies.
- Cost spike: disable fallback, compare resolution mix against 450/670/1010/1510
  internal cost units and the current official price page.
- Wallet discrepancy: stop both image routes, verify one reservation and one
  capture or release per generation, and reconcile `provider_usage` separately
  from user credits.
- Quality mismatch: rollback the fallback flag; do not silently redirect upscale
  or change the quoted SKU semantics.
