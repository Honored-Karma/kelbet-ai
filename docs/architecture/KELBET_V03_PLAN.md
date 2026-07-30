# KELBET AI v0.3 — Architecture & Implementation Plan

**Status:** Approved (2026-07-30)  
**Implementation:** Stage A/B in progress; later stages gated by DoD  
**Version target:** `0.3.0` (current codebase: `0.1.0`)

Related:

- [DATA_MODEL.md](./DATA_MODEL.md)
- [GENERATION_STATE_MACHINE.md](./GENERATION_STATE_MACHINE.md)

---

## 0. Executive summary

v0.3 turns KELBET from a bilingual bot + sync AI chat into a **production Mini App generation platform** on the existing modular monolith:

Telegram Mini App → catalog tool → upload/prompt → **server quote** → **reserve credits** → async generation (ARQ) → store assets (R2) → **capture or release** → history → deliver to user.

Preserve: integer ledger, idempotent wallet, thin handlers, `ChatProvider` for bot chat, RU/KK i18n, Postgres as SoT. Extend — do not rewrite — wallet with soft-hold reservations; add generation pipeline, secure Mini App auth, catalog, storage, queues, versioned API.

---

## 1. Audit of the existing project

### 1.1 Shape

| Layer | Path | Role |
|-------|------|------|
| Bot app | `apps/bot` | aiogram 3, thin handlers, Redis FSM |
| API app | `apps/api` | FastAPI, only `GET /health` |
| Domain package | `packages/kelbet` | models, repos, services, chat, i18n, config |
| Migrations | `migrations/versions/0001_initial.py` | users, wallets, credit_transactions |
| Tests | `tests/` | wallet, registration, concurrency, chat |
| Infra | `docker-compose.yml`, `docker/Dockerfile` | postgres:16, redis:7, api, bot, migrate |

No `docs/` (until this plan), no CI workflows, no Mini App, no generation/storage/worker, no `.env.example` (README references it — gap).

### 1.2 What works and must be preserved

1. **Integer credits** + `CHECK (balance >= 0)`.
2. **Immutable ledger** `credit_transactions` with unique `idempotency_key`.
3. **WalletService** credit/debit: `FOR UPDATE` + double idempotency check + nested transaction on `IntegrityError`.
4. **Welcome bonus** once: `welcome:{user_id}`.
5. **Registration** race-safe (`IntegrityError` paths) — covered by concurrent tests.
6. **ChatService**: validate → pre-check balance → provider → debit `chat:{request_id}` (sync path stays).
7. **ChatProvider Protocol** + `mock` / `openrouter` factory.
8. **i18n** `Msg` + `ru`/`kk` catalogs + `texts_for` for keyboards.
9. Layering: handlers/routes → services → repositories → models.
10. Alembic `0001_initial` — **never edit** after apply.

### 1.3 Gaps vs v0.3 product scenario

| Capability | Status |
|------------|--------|
| Mini App (React) | absent |
| Telegram initData auth / sessions | absent |
| Model catalog (DB) | absent (chat price in env only) |
| Generation jobs / attempts / assets | absent |
| Credit reserve/capture/release | absent (only immediate debit) |
| Object storage / presign | absent |
| ARQ workers / modality queues | Redis used only for FSM |
| Versioned business API | absent |
| Structured correlation logging | minimal ad-hoc logs |
| Webhooks, polling, DLQ | absent |
| Plans / payments | stub menu “coming soon” |
| CI | absent |

### 1.4 Known design debts (address in v0.3 without breaking chat)

- Chat: rare race (pre-check then provider then debit) can yield free answer if concurrent debit wins — acceptable for sync chat; generations must **reserve first**.
- `wallet.version` incremented but unused for CAS; `ConcurrentModificationError` unused — keep pessimistic locking; optionally use version in reservation updates.
- Chat cost hardcoded in settings — migrate text catalog entry later; bot chat may keep env cost in v0.3.0 for compatibility, with ADR to unify.

### 1.5 Patterns to extend (not replace)

```text
apps/bot | apps/api | apps/worker | apps/web (Mini App)
                    ↓
            packages/kelbet
              services / repositories / db / domain
              chat/          (keep)
              providers/     (new: generation adapters)
              storage/       (new)
              auth/          (new: initData + sessions)
              catalog/       (new)
              queue/         (new: ARQ tasks)
              i18n/          (extend)
```

---

## 2. Target directory structure

```text
kelbet_ai/
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py                 # session, auth user, settings
│   │   ├── middleware/             # correlation_id, timing
│   │   ├── errors.py               # problem+json mapping
│   │   └── routes/
│   │       ├── health.py           # liveness
│   │       ├── ready.py            # readiness (db+redis)
│   │       └── v1/
│   │           ├── auth.py
│   │           ├── me.py
│   │           ├── catalog.py
│   │           ├── generations.py
│   │           ├── uploads.py
│   │           ├── wallet.py
│   │           ├── history.py
│   │           └── webhooks.py     # provider callbacks
│   ├── bot/                        # existing + Mini App button / notify hooks
│   ├── worker/
│   │   ├── main.py                 # ARQ worker entry
│   │   ├── settings_arq.py
│   │   └── tasks/
│   │       ├── generate_text.py
│   │       ├── generate_image.py
│   │       ├── generate_video.py
│   │       ├── poll_provider.py
│   │       ├── sweep_stuck.py
│   │       ├── sweep_reservations.py
│   │       ├── gc_assets.py
│   │       └── notify_telegram.py
│   └── web/                        # Telegram Mini App
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json           # strict
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── app/                # router, providers
│           ├── pages/              # Home, Create, Generation, History, Plans, Profile
│           ├── features/           # generation form, upload, wallet badge
│           ├── shared/             # api client, i18n, ui states, telegram theme
│           └── styles/
├── packages/kelbet/
│   ├── auth/
│   │   ├── init_data.py            # HMAC validate, auth_date, replay
│   │   └── session.py
│   ├── catalog/
│   │   └── pricing.py              # integer quote engine
│   ├── providers/
│   │   ├── base.py                 # GenerationProvider Protocol
│   │   ├── factory.py
│   │   ├── mock/
│   │   ├── openrouter/             # text generations (API path)
│   │   └── runway/                 # image + video (+ edit/upscale as available)
│   ├── storage/
│   │   ├── base.py
│   │   ├── r2.py
│   │   ├── validation.py           # mime, size, magic bytes
│   │   └── keys.py                 # safe object keys
│   ├── queue/
│   │   └── names.py                # queue constants
│   ├── services/
│   │   ├── wallet.py               # EXTEND: reserve/capture/release/refund
│   │   ├── generation.py           # orchestration
│   │   ├── generation_sm.py        # transitions
│   │   ├── catalog.py
│   │   ├── upload.py
│   │   ├── history.py
│   │   └── ... existing
│   ├── repositories/               # + generation, catalog, session, assets
│   ├── db/models/                  # + new ORM models
│   ├── domain/                     # enums, exceptions extended
│   ├── observability/
│   │   └── logging.py              # JSON logs, redaction
│   ├── chat/                       # UNCHANGED contract
│   └── i18n/                       # + Mini App / API error strings as needed
├── migrations/versions/
│   ├── 0001_initial.py             # IMMUTABLE
│   ├── 0002_…                      # additive only
│   └── …
├── docs/architecture/              # this folder
├── docs/adr/                       # ADR-001…
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/                  # provider contract tests
│   └── e2e/
├── docker-compose.yml              # + worker (+ optional minio for local R2)
└── pyproject.toml                  # + arq, boto3/aiobotocore, python-jose/or PyJWT, etc.
```

Frontend lives in-repo as `apps/web` (Vite monorepo sibling). Backend remains one Python package.

---

## 3. ER schema

See **[DATA_MODEL.md](./DATA_MODEL.md)** for full column-level design.

Summary of new entities: `auth_sessions`, `catalog_models`, `credit_reservations`, `generation_jobs`, `generation_attempts`, `generation_assets`, `provider_usage`, `webhook_receipts`, `feature_flags`; wallet gains `reserved`.

---

## 4. Generation state machine

See **[GENERATION_STATE_MACHINE.md](./GENERATION_STATE_MACHINE.md)**.

Credit coupling: **reserve on create → capture on success XOR release on fail/cancel/timeout**.

---

## 5. API contracts (`/api/v1`)

### 5.1 Conventions

- Base: `/api/v1`
- Auth: `Authorization: Bearer <session_token>` (except auth + health)
- Idempotency: header `Idempotency-Key` on create generation / reserve-sensitive ops
- Errors: JSON problem shape (OpenAPI component `ErrorResponse`):

```json
{
  "error": {
    "code": "insufficient_credits",
    "message": "Not enough credits",
    "details": { "required": 12, "available": 3 },
    "correlation_id": "uuid"
  }
}
```

- No prompt content in error logs; API may return safe validation messages only.
- CORS: allowlist of Mini App origins (env).
- OpenAPI: generated by FastAPI; export committed or CI artifact `docs/openapi/v1.json` in a later stage.

### 5.2 Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | no | Liveness (keep; also `/api/v1/health` alias optional) |
| GET | `/api/v1/ready` | no | DB + Redis ping |
| POST | `/api/v1/auth/telegram` | no | Validate initData → session token |
| POST | `/api/v1/auth/logout` | yes | Revoke session |
| GET | `/api/v1/me` | yes | Profile, language, plan, balances |
| PATCH | `/api/v1/me` | yes | language |
| GET | `/api/v1/catalog/models` | yes | Enabled models for user (flags applied) |
| GET | `/api/v1/catalog/models/{slug}` | yes | Detail + capabilities |
| POST | `/api/v1/wallet/quote` | yes | Server price for model+params |
| GET | `/api/v1/wallet` | yes | `balance`, `reserved`, `available` |
| GET | `/api/v1/wallet/transactions` | yes | Ledger page (no sensitive meta) |
| POST | `/api/v1/uploads/presign` | yes | Presigned PUT for input |
| POST | `/api/v1/uploads/{id}/complete` | yes | Confirm + magic-byte validate |
| POST | `/api/v1/generations` | yes | Quote+reserve+create+enqueue (or split) |
| GET | `/api/v1/generations/{id}` | yes | Status/progress/results (**owner only**) |
| POST | `/api/v1/generations/{id}/cancel` | yes | Cancel |
| GET | `/api/v1/history` | yes | Paginated works |
| POST | `/api/v1/webhooks/{provider}` | secret | Provider callbacks |

### 5.3 Key payloads (sketch)

**POST `/auth/telegram`**

```json
{ "init_data": "<raw query string from Telegram.WebApp.initData>" }
```

Response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "uuid", "language": "kk", "plan": "free" }
}
```

**POST `/wallet/quote`**

```json
{
  "model_slug": "runway-gen4-image",
  "params": { "aspect_ratio": "1:1", "resolution": "720p" }
}
```

Response:

```json
{
  "model_slug": "runway-gen4-image",
  "user_credit_price": 8,
  "currency": "credits",
  "quote_id": "uuid",
  "expires_at": "…"
}
```

Frontend displays only this price.

**POST `/generations`**

```json
{
  "model_slug": "runway-gen4-image",
  "prompt": "…",
  "params": { "aspect_ratio": "1:1" },
  "input_asset_ids": [],
  "quote_id": "uuid"
}
```

Headers: `Idempotency-Key: …`

Response `201`:

```json
{
  "id": "uuid",
  "status": "queued",
  "user_credit_price": 8,
  "reservation_id": "uuid",
  "progress_pct": 0
}
```

**GET `/generations/{id}`** (owner check)

Includes status, progress, output asset download URLs (short-lived presigned GET), error_code if any.

### 5.4 Ownership / IDOR

Every resource fetch joins `user_id == auth.user_id`. Cross-user UUID → `404` (not `403`) to avoid existence leaks.

---

## 6. Migration plan

| Revision | Purpose | Risk |
|----------|---------|------|
| `0001_initial` | Existing — **do not modify** | — |
| `0002_wallet_reserved` | `wallets.reserved`, CHECKs; minimal `credit_reservations` | low; default 0 |
| `0003_auth_sessions` | Mini App sessions | low |
| `0004_catalog` | `catalog_models`, `feature_flags`, `price_quotes` + seeds | low |
| `0005_assets` | `generation_assets` (uploads; generation FK later) | low |
| `0006_generation_core` | jobs, attempts, provider_usage, webhook_receipts; FK assets/reservations | medium |

Rules:

- Only additive migrations.
- Seeds use idempotent `ON CONFLICT DO NOTHING` where needed.
- Expand `TxReason` in Python enums without DB enum type (strings already).

---

## 7. ADR list

Create under `docs/adr/` after approval (titles locked here):

| ID | Title | Decision summary |
|----|-------|------------------|
| ADR-001 | Modular monolith for v0.3 | Single deployable domain; apps = api/bot/worker/web; no microservices/Kafka/K8s |
| ADR-002 | Soft-hold credit reservations | `balance` + `reserved`; capture debits ledger; release frees hold without ledger credit |
| ADR-003 | Postgres SoT, Redis for queue/FSM/replay | ARQ on Redis; all business state in Postgres |
| ADR-004 | Telegram initData-only Mini App auth | Server HMAC validate; ignore `initDataUnsafe`; short-lived opaque sessions |
| ADR-005 | DB-backed model catalog | Frontend never prices; quotes from catalog + integer pricing engine |
| ADR-006 | Provider adapter ports | OpenRouter text; Runway image/video first; Mock for tests; future OpenAI/Google adapters |
| ADR-007 | R2 for assets | Presigned upload; magic-byte check; no user URL fetch (anti-SSRF) |
| ADR-008 | Generation state machine | Explicit statuses; transactional transitions; webhook + poll |
| ADR-009 | Sync chat vs async generation billing | Chat keeps post-success debit; generations reserve-first |
| ADR-010 | Observability redaction | JSON logs with correlation/generation ids; never log prompts, tokens, initData |
| ADR-011 | Integer economics | No floats for credits or provider cost subunits |
| ADR-012 | API versioning | `/api/v1` + OpenAPI; health outside or mirrored |

---

## 8. Vertical implementation stages

Each stage is a **thin vertical slice** with its own DoD. No big-bang.

### Stage A — Foundations & docs hygiene

- Add `.env.example`, architecture docs (this), ADR stubs.
- Observability helper (JSON logger, `correlation_id` middleware skeleton).
- Compose: worker service stub (no-op health).
- **DoD:** docs merged; app still boots; existing tests green.

### Stage B — Wallet reserve/capture/release

- Migration `0002`; extend `WalletService`.
- Unit + concurrent reservation tests; impossible negative balance tests.
- **DoD:** reserve→capture and reserve→release idempotent under concurrency; chat tests still pass.

### Stage C — Mini App auth + `/api/v1/me`

- initData validation, replay cache, sessions, CORS allowlist.
- Routes: auth, me, ready.
- Integration tests for forged/expired/replayed initData.
- **DoD:** cannot call `/me` without valid session; unsafe client fields ignored.

### Stage D — Catalog + quote API

- Migration catalog; seed mock models; `GET catalog`, `POST wallet/quote`.
- Feature flags filter.
- **DoD:** changing DB price changes API quote without frontend deploy.

### Stage E — Uploads + R2 (or MinIO local)

- Presign, complete, magic bytes, size/mime limits, safe keys.
- **DoD:** contract tests for validation; SSRF test ensures no remote URL fetch API.

### Stage F — Generation pipeline + MockProvider (image)

- Migrations jobs/reservations/assets; state machine; ARQ `image` queue.
- `POST/GET/cancel generations`; history list.
- E2E happy path with MockProvider + Postgres + Redis.
- **DoD:** full wallet lifecycle on success/fail/cancel; duplicate webhook test.

### Stage G — OpenRouter text generations (API)

- Text queue; adapter reuse patterns from chat; catalog text model.
- Bot chat remains on existing `ChatService` (ADR-009).
- **DoD:** Mini App text generation uses reserve/capture; bot chat regression green.

### Stage H — Runway image/video

- Runway adapter; webhooks + polling; separate `video` queue + concurrency limits.
- **DoD:** contract tests with recorded fixtures; timeout/release path covered.

### Stage I — Mini App UI

- Vite React TS strict; TanStack Query; Router; Zod; telegram theme; ru/kk.
- Pages: Home, Create, Generation, History, Plans (read-only stub ok), Profile.
- Skeleton / empty / error / offline states.
- **DoD:** mobile-first flows against mock API; no client-side price invention.

### Stage J — Hardening

- Rate limits, per-user concurrency, provider rate limits, graceful worker shutdown, stuck sweeper, retention GC.
- Metrics-ready counters (naming doc); OpenAPI export; CI workflow.
- **DoD:** checklist in §11 Stage J met; security review pass.

---

## 9. Files to create or change (planned)

### 9.1 Create

**Docs:** `docs/architecture/*` (done in this PR-of-docs), `docs/adr/ADR-001…012.md`

**Backend package:**  
`packages/kelbet/auth/*`, `catalog/*`, `providers/**`, `storage/*`, `queue/*`, `observability/*`,  
new models/repos/services listed in §2,  
`migrations/versions/0002_*.py` … `0007_*.py`

**Apps:**  
`apps/api/deps.py`, `errors.py`, `middleware/*`, `routes/v1/*`, `routes/ready.py`,  
`apps/worker/**`,  
`apps/web/**` (full Mini App tree)

**Tests:** `tests/unit/**`, `tests/integration/**`, `tests/contracts/**`, `tests/e2e/**`

**Infra:** worker in `docker-compose.yml`, optional `minio` service, `.env.example`, `.github/workflows/ci.yml`

### 9.2 Change (carefully)

| File | Change |
|------|--------|
| `packages/kelbet/services/wallet.py` | add reserve/capture/release/refund |
| `packages/kelbet/db/models/wallet.py` | `reserved` column |
| `packages/kelbet/domain/enums.py` | statuses, modalities, tx reasons |
| `packages/kelbet/domain/exceptions.py` | generation/auth/storage errors |
| `packages/kelbet/config.py` | auth, R2, ARQ, CORS, Runway, session TTL |
| `packages/kelbet/i18n/ru.py`, `kk.py`, `keys.py` | new strings |
| `apps/api/main.py` | mount v1 routers, CORS, middleware |
| `apps/bot/handlers/menu.py` | wire WebApp URL / remove stubs gradually |
| `apps/bot/keyboards/__init__.py` | Mini App button |
| `apps/bot/main.py` | optional notify dependency wiring |
| `pyproject.toml` | version 0.3.0, deps arq, jwt, aiobotocore, … |
| `docker-compose.yml` | worker (+ minio) |
| `README.md` | v0.3 architecture pointer |
| `tests/conftest.py` | redis fixtures, auth helpers |

### 9.3 Do not change

- `migrations/versions/0001_initial.py`
- Existing chat debit semantics (unless Stage G explicitly unifies — out of default scope)
- Destructive DB commands / drop tables in migrations

---

## 10. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Provider ambiguity after timeout | Double generation / billing confusion | Provider idempotency keys; poll before retry; prefer release only when sure unused |
| Soft-hold drift (`reserved` ≠ sum held) | Wrong available balance | Periodic reconcile job; single code path for reserved mutations |
| Runway API shape changes | Broken video/image | Adapter isolation + contract tests + feature flags |
| Large video cost / queue backup | UX + money | Per-user limits, video concurrency=low, clear quote before start |
| initData replay / clock skew | Auth bypass or lockout | auth_date window + Redis replay; NTP; reject future skew |
| Prompt leakage in logs/support | Privacy/compliance | Redaction middleware; store prompts encrypted or separately; ADR-010 |
| R2 misconfig public buckets | Data leak | Private ACL; presigned GET only; bucket policies in runbook |
| Mini App CORS / Telegram origin quirks | Login failures | Document exact origins; staging bot |
| Scope creep (payments, plans) | Delay v0.3 | Plans page stub; payments = v0.4 |
| Chat vs generation dual billing mental model | Dev mistakes | ADR-009; separate services; shared wallet primitives only |

---

## 11. Stage readiness criteria

### Stage A

- [ ] Architecture docs + ADR index present
- [ ] `.env.example` matches `Settings`
- [ ] `pytest`, existing suite green
- [ ] No behavior change to bot chat

### Stage B

- [ ] `reserved` migration applied on clean DB
- [ ] Concurrent reserve cannot oversell available credits
- [ ] Capture/release/refund idempotent
- [ ] `balance >= 0` and `balance >= reserved` always
- [ ] Chat debit tests still green

### Stage C

- [ ] Valid initData → token → `/me`
- [ ] Tampered hash / expired auth_date / replay → 401
- [ ] `initDataUnsafe` never used server-side
- [ ] Ownership-ready session model

### Stage D

- [ ] Catalog prices only from DB
- [ ] Disabled/deprecated models hidden or flagged
- [ ] Quote matches integer pricing rules
- [ ] Localization fields returned for ru/kk

### Stage E

- [ ] Presign rejects bad content-type/size
- [ ] Complete rejects failed magic bytes
- [ ] Object keys non-guessable
- [ ] No endpoint fetches arbitrary user URLs

### Stage F

- [ ] E2E MockProvider: create→succeed→capture→history asset
- [ ] Fail path releases credits
- [ ] Cancel queued releases credits
- [ ] Duplicate webhook → single capture
- [ ] State illegal transitions rejected
- [ ] IDOR: other user’s generation → 404

### Stage G

- [ ] Text generation via API uses OpenRouter adapter + reserve flow
- [ ] Bot `ChatService` regression suite green
- [ ] Provider errors don’t capture

### Stage H

- [ ] Image + video paths via Runway behind flag
- [ ] Polling works with webhooks disabled
- [ ] Video queue concurrency limit enforced
- [ ] Timeout → timed_out + release

### Stage I

- [ ] All six pages routable; theme vars applied
- [ ] Skeleton/empty/error/offline implemented on main flows
- [ ] UI shows only server quotes
- [ ] ru/kk switch works with profile language

### Stage J

- [x] Rate limiting on auth + generations
- [x] Graceful worker shutdown (no lost “running” without recovery)
- [x] Stuck job sweeper tested
- [x] CI: lint + typecheck + pytest
- [x] OpenAPI published
- [x] Security checklist (§12) signed off

---

## 12. Cross-cutting designs (condensed)

### 12.1 Telegram Mini App

- React + TypeScript **strict** + Vite + TanStack Query + React Router + Zod
- Telegram theme CSS variables (`--tg-theme-*`)
- Mobile-first; pages: Home, Create, Generation, History, Plans, Profile
- States: skeleton, empty, error, offline (navigator + query focus)
- i18n ru/kk aligned with backend `users.language`

### 12.2 Auth security

1. Parse raw `initData`.
2. HMAC-SHA256 with `BOT_TOKEN` per Telegram WebApp algorithm (`WebAppData` key).
3. Check `auth_date` within `TELEGRAM_AUTH_MAX_AGE_SECONDS` (e.g. 300–86400 configurable; default tight for session issue).
4. Replay: store hash of initData in Redis with TTL; reject duplicates.
5. Upsert user (reuse registration paths / link telegram_id).
6. Issue opaque session token; store **hash** in `auth_sessions`.
7. Never trust `initDataUnsafe`.

### 12.3 Wallet flow

`quote → reserve → (work) → capture | release` (+ `refund` post-capture).  
See DATA_MODEL + state machine. Parallel debit protection: `SELECT wallet FOR UPDATE` on all mutations.

### 12.4 Providers

| Provider | Modalities | Role |
|----------|------------|------|
| Mock | all | dev/tests |
| OpenRouter | text | Mini App text (+ existing bot chat provider) |
| Runway | image, image_edit, video, upscale (as API allows) | first media provider |
| Future | — | OpenAI, Google adapters implementing same Protocol |

### 12.5 Queues (Redis + ARQ)

| Queue | Purpose | Concurrency (initial) |
|-------|---------|------------------------|
| `kelbet:text` | text generations | higher |
| `kelbet:image` | image / edit / upscale | medium |
| `kelbet:video` | video | low (1–2) |
| `kelbet:maintain` | sweep, GC, poll | low |

Per-user active job limits in Redis+DB check before enqueue. Provider rate limits in adapter (token bucket). Graceful shutdown: stop dequeue, finish current, requeue if needed. Stuck recovery via maintain tasks.

### 12.6 Observability

Structured JSON fields: `timestamp`, `level`, `message`, `correlation_id`, `generation_id`, `user_id` (uuid ok), `provider`, `model`, `latency_ms`, `provider_cost_units`, `user_credit_price`, `status`.  
**Never:** prompt text, completion text, raw initData, bearer tokens, file bytes.

Health: `/health` liveness; `/api/v1/ready` for Postgres+Redis. Metrics-ready: counters/histograms behind a thin `Metrics` protocol (noop default; Prometheus later).

### 12.7 Security checklist

- [ ] Secrets only via env
- [ ] Webhook signature/secret
- [ ] Rate limiting
- [ ] Zod (FE) + Pydantic (BE) validation
- [ ] Ownership checks / anti-IDOR
- [ ] CORS allowlist
- [ ] Input sanitization (lengths, mime, magic)
- [ ] No tokens/PII prompts in logs
- [ ] Presigned URLs short TTL

### 12.8 Test plan (mapping)

| Area | Tests |
|------|-------|
| Unit | pricing integer math, state transitions, initData crypto, magic bytes |
| Integration | Postgres wallet reservation races; Redis replay; ARQ job with MockProvider |
| Contracts | OpenRouter/Runway/Mock adapter fixtures |
| Concurrent reservation | many parallel reserves |
| Duplicate webhook | single side effect |
| Failed generation refund/release | balance restored |
| Cancelled generation | release |
| Mini App auth | forge/expiry/replay |
| File validation | mime/size/magic |
| Localization | catalog + API messages ru/kk |
| E2E | happy path MockProvider end-to-end |

---

## 13. Out of scope for v0.3

- Real payment acquiring / Kaspi / Stripe
- Paid plan entitlements beyond catalog flags
- Kubernetes, Kafka, multi-region
- Rewriting bot chat to reserve-first (unless explicitly pulled in)
- Editing or squashing `0001_initial`
- Microservices split

---

## 14. Approval gate

**Please confirm or request changes on:**

1. Soft-hold wallet model (`balance` + `reserved`) vs alternative “debit-on-reserve”
2. Opaque session tokens vs JWT access tokens
3. Runway-first media (vs separate image provider earlier)
4. Stage order A→J
5. Plans page stub (no payments) in v0.3

After written approval, implementation starts at **Stage A/B** only as agreed — still no unrelated refactors.
