# Security checklist (v0.3 + moderation minimum)

Signed off for the modular monolith as of Stage J.

| Item | Status | Notes |
|------|--------|-------|
| Secrets only via env | done | `.env` / compose env; no secrets in repo |
| Webhook signature/secret | done | `WEBHOOK_SECRET` + `X-Kelbet-Webhook-Secret` |
| Rate limiting | done | Auth (IP) + generations (user) Redis/memory windows |
| Zod (FE) + Pydantic (BE) | done | Mini App Zod schemas; FastAPI models |
| Ownership / anti-IDOR | done | Generation/upload/history scoped to session user |
| CORS allowlist | done | `CORS_ORIGINS` |
| Input sanitization | done | lengths, mime, magic bytes; no user URL fetch |
| No tokens/PII prompts in logs | done | JSON redaction (ADR-010) |
| Presigned URLs short TTL | done | `S3_PRESIGN_TTL_SECONDS` default 600 |
| Text moderation before billing | done | Generation/chat/prompt assistant call `ModerationService`; generation runs before reserve/enqueue |
| Privacy-safe moderation record | done | SHA-256 input hash, policy version and bounded reason codes; no raw prompt/provider body |
| Moderation operating mode | done | `report` by default; `block` and `off` require explicit server config |
| Photo rights/consent | done | Image edit and image-to-video require current version; version/timestamp/asset IDs are stored |
| Operator review RBAC | done | Support reads metadata-only queue; only admin records idempotent reviewed outcome + audit |
| Permanent auto-ban from moderation | not implemented by design | Repeat signals escalate to review/rejection, never a permanent user block |
| Image content classifier | not implemented | Current pipeline validates files and moderates text only; API/UI expose `image_moderation_supported=false` |
| External moderation privacy/region review | production gate | OpenAI text adapter is opt-in; provider terms, region and data handling require owner review before enablement |

Additional Stage J controls: stuck sweeper → `timed_out` + release; per-user active generation cap; ARQ `job_timeout` + maintain recovery.

## Moderation invariants

1. A moderation `block` or moderation-layer rate limit is committed as an investigation
   record but cannot create a reservation or queue item.
2. Logs, Sentry, audit and operator DTOs must never contain prompt text, image bytes,
   provider response bodies, Telegram initData or authorization headers.
3. `provider_unavailable` is a technical reason and is not counted as a prior content
   violation. `open` records/report-routes the outage; `closed` rejects before billing.
4. RU/KK local rules are a phrase/obfuscation baseline only. Do not describe them as
   semantic or image moderation.
5. Rollback order is `block -> report -> off`. Do not delete decisions or consent records.
