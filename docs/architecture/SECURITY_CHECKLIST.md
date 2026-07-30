# Security checklist (v0.3 Stage J)

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

Additional Stage J controls: stuck sweeper → `timed_out` + release; per-user active generation cap; ARQ `job_timeout` + maintain recovery.
