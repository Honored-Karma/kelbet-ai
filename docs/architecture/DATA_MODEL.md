# KELBET AI v0.3 — Data Model (ER)

**Status:** Implemented locally through additive migration `0017_referral_mvp`; external
deployment remains unverified.
**Source of truth:** PostgreSQL  
**Constraint:** Migration `0001_initial` is immutable; all changes are additive revisions.

Related: [KELBET_V03_PLAN.md](./KELBET_V03_PLAN.md) · [GENERATION_STATE_MACHINE.md](./GENERATION_STATE_MACHINE.md)

---

## 1. ER overview

```text
users 1──1 wallets 1──* credit_transactions
  │           │
  │           └──* credit_reservations *──1 generation_jobs
  │
  ├──* auth_sessions
  ├──* generation_jobs 1──* generation_attempts
  │         │            1──* generation_assets
  │         │            1──* provider_usage
  │         └──* generation_job_events (optional audit)
  │
  └──* uploads (input assets pending / bound)

users 1──1 referral_codes
users 1──* referral_attributions (inviter)
users 1──0..1 referral_attributions (invited, immutable)
referral_attributions 1──1 referral_rewards *──0..1 payment_orders

catalog_models (standalone, referenced by generation_jobs.model_id)
feature_flags (standalone)
```

---

## 2. Existing tables (preserve)

### 2.1 `users` (0001_initial)

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `telegram_id` | BIGINT UNIQUE | identity for bot + Mini App |
| `username` | VARCHAR(255) NULL | |
| `language` | VARCHAR(5) | `ru` \| `kk` |
| `plan` | VARCHAR(32) | currently `free` |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

**Operator additive columns (migration 0012):**

| Column | Type | Notes |
|--------|------|--------|
| `is_blocked` | BOOLEAN NOT NULL DEFAULT false | soft ban |
| `blocked_at` | TIMESTAMPTZ NULL | time of current block |
| `blocked_reason` | VARCHAR(64) NULL | safe reason code, never free-form PII/prompt |

### 2.2 `wallets` (0001_initial)

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `user_id` | UUID UNIQUE FK → users | CASCADE |
| `balance` | INT NOT NULL, CHECK ≥ 0 | total credits owned |
| `version` | INT NOT NULL | bumped on money-moving ops |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

**v0.3 additive columns:**

| Column | Type | Notes |
|--------|------|--------|
| `reserved` | INT NOT NULL DEFAULT 0, CHECK ≥ 0 | soft-held credits |
| CHECK | `balance >= reserved` | available = balance − reserved |

Semantics:

- `balance` — owned credits (including held).
- `reserved` — currently held for in-flight jobs.
- `available = balance - reserved` — spendable for new quotes/reserves.
- Ledger rows are written only on **capture** (debit) and **release is not a ledger credit** when using soft-hold; **refund** after capture writes a credit row. See wallet flow in the plan.

### 2.3 `credit_transactions` (0001_initial)

Immutable ledger. No schema change required for core columns.

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `wallet_id` | UUID FK → wallets | |
| `amount` | INT | signed: +credit / −debit |
| `balance_after` | INT | snapshot of `wallets.balance` |
| `type` | VARCHAR(32) | `credit` \| `debit` |
| `reason` | VARCHAR(64) | extended enums below |
| `idempotency_key` | VARCHAR(128) UNIQUE | |
| `meta` | JSONB NULL | no prompt text |
| `created_at` | TIMESTAMPTZ | |

**New `TxReason` values (app enum; DB remains string):**

| Reason | Direction | When |
|--------|-----------|------|
| `welcome_bonus` | credit | existing |
| `ai_chat` | debit | existing (sync chat) |
| `generation_capture` | debit | finalize reservation |
| `generation_refund` | credit | post-capture refund |
| `admin_adjust` | either | future ops (feature-flagged) |
| `plan_grant` | credit | future plans/top-ups |

Idempotency key patterns:

| Op | Key |
|----|-----|
| Welcome | `welcome:{user_id}` |
| Chat | `chat:{request_id}` |
| Capture | `capture:{reservation_id}` |
| Refund | `refund:{reservation_id}` or `refund:{generation_id}:{n}` |

---

## 3. New tables

### 3.1 `auth_sessions`

Short-lived server sessions for Mini App (opaque token hash stored; raw token only in client).

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `user_id` | UUID FK → users ON DELETE CASCADE | |
| `token_hash` | CHAR(64) UNIQUE | SHA-256 of bearer token |
| `telegram_auth_date` | TIMESTAMPTZ NOT NULL | from initData |
| `init_data_hash` | CHAR(64) NOT NULL | HMAC digest of validated initData (replay binding) |
| `expires_at` | TIMESTAMPTZ NOT NULL | e.g. 24h or 1h sliding |
| `revoked_at` | TIMESTAMPTZ NULL | logout / rotate |
| `user_agent` | VARCHAR(512) NULL | optional |
| `ip_hash` | CHAR(64) NULL | optional privacy-preserving |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Indexes: `(user_id)`, `(expires_at)` WHERE `revoked_at IS NULL`.

Replay: Redis key `tg_init:{init_data_hash}` TTL = max(auth_date window, session issue window); DB unique on recent hashes optional.

### 3.2 `catalog_models`

Server-side model catalog. Frontend never hardcodes prices.

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `slug` | VARCHAR(64) UNIQUE | stable API id, e.g. `runway-gen4-image` |
| `modality` | VARCHAR(32) NOT NULL | `text` \| `image` \| `image_edit` \| `video` \| `upscale` |
| `provider` | VARCHAR(32) NOT NULL | `openrouter` \| `runway` \| `mock` \| … |
| `provider_model_id` | VARCHAR(128) NOT NULL | upstream model string |
| `display_order` | INT NOT NULL DEFAULT 100 | |
| `enabled` | BOOLEAN NOT NULL DEFAULT true | |
| `deprecated_at` | TIMESTAMPTZ NULL | soft deprecation |
| `replacement_slug` | VARCHAR(64) NULL | optional |
| `feature_flag` | VARCHAR(64) NULL | if set, require flag |
| `user_credit_price` | INT NOT NULL, CHECK > 0 | **what user pays** |
| `provider_cost_units` | INT NOT NULL DEFAULT 0, CHECK ≥ 0 | internal cost in **milli-credits or USD micros** — integer only; unit documented in settings (`PROVIDER_COST_UNIT=usd_micros`) |
| `currency_hint` | VARCHAR(8) NULL | display only, e.g. `USD` for ops |
| `capabilities` | JSONB NOT NULL | see schema below |
| `input_requirements` | JSONB NOT NULL | see schema below |
| `localization` | JSONB NOT NULL | `{ "ru": {...}, "kk": {...} }` |
| `pricing_rules` | JSONB NULL | duration/resolution multipliers (integer factors) |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

**`capabilities` (example):**

```json
{
  "aspect_ratios": ["1:1", "16:9", "9:16"],
  "resolutions": ["720p", "1080p"],
  "durations_sec": [5, 10],
  "max_prompt_chars": 2000,
  "supports_negative_prompt": false,
  "supports_seed": true,
  "max_outputs": 1
}
```

**`input_requirements` (example):**

```json
{
  "prompt": "required",
  "source_image": "optional",
  "mask_image": "forbidden",
  "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
  "max_input_bytes": 10485760
}
```

**`localization` (example):**

```json
{
  "ru": { "name": "Изображение Gen-4", "description": "…" },
  "kk": { "name": "Gen-4 сурет", "description": "…" }
}
```

Seeded via migration data + admin/ops updates later. Never trust client-sent price.

### 3.3 `credit_reservations`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `wallet_id` | UUID FK → wallets | |
| `user_id` | UUID FK → users | denormalized for ownership checks |
| `generation_id` | UUID NULL FK → generation_jobs | set when job created |
| `amount` | INT NOT NULL, CHECK > 0 | user credit units held |
| `status` | VARCHAR(32) NOT NULL | `held` \| `captured` \| `released` \| `expired` |
| `idempotency_key` | VARCHAR(128) UNIQUE | client/server key for reserve |
| `quote_snapshot` | JSONB NOT NULL | model_id, price, pricing_rules applied, catalog version |
| `capture_tx_id` | UUID NULL FK → credit_transactions | |
| `refund_tx_id` | UUID NULL FK → credit_transactions | |
| `expires_at` | TIMESTAMPTZ NOT NULL | stale hold sweeper |
| `held_at` / `finalized_at` | TIMESTAMPTZ | |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Indexes: `(wallet_id, status)`, `(expires_at)` WHERE `status = 'held'`, `(generation_id)`.

Invariant: at most one active (`held`) reservation per generation; capture/release/refund are terminal and idempotent.

### 3.4 `generation_jobs`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | public `generation_id` |
| `user_id` | UUID FK → users | |
| `model_id` | UUID FK → catalog_models | |
| `modality` | VARCHAR(32) NOT NULL | denormalized from catalog |
| `status` | VARCHAR(32) NOT NULL | see state machine doc |
| `idempotency_key` | VARCHAR(128) NOT NULL | UNIQUE(user_id, idempotency_key) |
| `request_hash` | CHAR(64) NOT NULL | SHA-256 of canonical request |
| `prompt_redacted` | BOOLEAN NOT NULL DEFAULT true | prompts stored separately/encrypted or omitted from logs |
| `params` | JSONB NOT NULL | aspect, resolution, duration, seed — **no raw secrets** |
| `prompt_storage_key` | VARCHAR(512) NULL | optional encrypted object or DB vault ref; prefer not logging |
| `input_asset_ids` | UUID[] NULL | or junction table |
| `reservation_id` | UUID NULL FK → credit_reservations | |
| `user_credit_price` | INT NOT NULL | snapshot at quote time |
| `provider` | VARCHAR(32) NOT NULL | |
| `provider_model_id` | VARCHAR(128) NOT NULL | |
| `provider_job_id` | VARCHAR(128) NULL | upstream async id |
| `progress_pct` | INT NOT NULL DEFAULT 0, CHECK 0–100 | |
| `progress_stage` | VARCHAR(64) NULL | `queued` \| `uploading` \| `generating` \| … |
| `error_code` | VARCHAR(64) NULL | stable machine code |
| `error_class` | VARCHAR(32) NULL | `user` \| `provider` \| `internal` \| `timeout` |
| `attempt_count` | INT NOT NULL DEFAULT 0 | |
| `max_attempts` | INT NOT NULL DEFAULT 3 | |
| `queued_at` / `started_at` / `finished_at` | TIMESTAMPTZ NULL | |
| `cancel_requested_at` | TIMESTAMPTZ NULL | |
| `dead_letter_at` | TIMESTAMPTZ NULL | |
| `next_poll_at` | TIMESTAMPTZ NULL | polling fallback |
| `webhook_last_event_id` | VARCHAR(128) NULL | duplicate webhook protection |
| `correlation_id` | UUID NOT NULL | tracing |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Indexes:

- `(user_id, created_at DESC)` — history
- `(status, next_poll_at)` — poller / sweeper
- `(provider, provider_job_id)` UNIQUE WHERE `provider_job_id IS NOT NULL`
- `(status)` WHERE status IN active set

### 3.5 `generation_attempts`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `generation_id` | UUID FK → generation_jobs ON DELETE CASCADE | |
| `attempt_no` | INT NOT NULL | 1..N |
| `status` | VARCHAR(32) NOT NULL | `started` \| `succeeded` \| `failed` \| `timed_out` \| `cancelled` |
| `provider_request_id` | VARCHAR(128) NULL | |
| `provider_job_id` | VARCHAR(128) NULL | |
| `latency_ms` | INT NULL | |
| `error_code` | VARCHAR(64) NULL | |
| `error_message_safe` | VARCHAR(512) NULL | sanitized, no user prompt |
| `raw_response_meta` | JSONB NULL | status codes, headers subset — no bodies with PII |
| `started_at` / `finished_at` | TIMESTAMPTZ | |
| UNIQUE | `(generation_id, attempt_no)` | |

### 3.6 `generation_assets`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `generation_id` | UUID NULL FK → generation_jobs | NULL for unbound uploads |
| `user_id` | UUID FK → users | ownership |
| `role` | VARCHAR(32) NOT NULL | `input` \| `mask` \| `output` \| `thumb` |
| `storage_backend` | VARCHAR(32) NOT NULL | `r2` |
| `bucket` | VARCHAR(128) NOT NULL | |
| `object_key` | VARCHAR(512) NOT NULL | UUID-based safe name |
| `content_type` | VARCHAR(128) NOT NULL | validated |
| `byte_size` | INT NOT NULL | |
| `sha256` | CHAR(64) NULL | after finalize |
| `magic_ok` | BOOLEAN NOT NULL DEFAULT false | magic-byte check passed |
| `visibility` | VARCHAR(32) NOT NULL | `private` |
| `retention_class` | VARCHAR(32) NOT NULL | `temp_input` \| `permanent_output` |
| `expires_at` | TIMESTAMPTZ NULL | temp inputs |
| `deleted_at` | TIMESTAMPTZ NULL | soft delete / GC |
| `created_at` / `updated_at` | TIMESTAMPTZ | |
| UNIQUE | `(bucket, object_key)` | |

**No user-supplied URLs as fetch sources** — only `asset_id` references after upload. Prevents SSRF.

### 3.7 `provider_usage`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `generation_id` | UUID FK → generation_jobs | |
| `attempt_id` | UUID NULL FK → generation_attempts | |
| `provider` | VARCHAR(32) NOT NULL | |
| `provider_model_id` | VARCHAR(128) NOT NULL | |
| `modality` | VARCHAR(32) NOT NULL | |
| `provider_cost_units` | INT NOT NULL DEFAULT 0 | integer micros / milli |
| `user_credit_price` | INT NOT NULL | snapshot |
| `latency_ms` | INT NULL | |
| `http_status` | INT NULL | |
| `tokens_in` / `tokens_out` | INT NULL | text models |
| `meta` | JSONB NULL | non-sensitive |
| `created_at` | TIMESTAMPTZ | |

### 3.8 `webhook_receipts`

Duplicate webhook protection (provider callbacks).

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `provider` | VARCHAR(32) NOT NULL | |
| `event_id` | VARCHAR(128) NOT NULL | provider delivery id |
| `generation_id` | UUID NULL | |
| `payload_hash` | CHAR(64) NOT NULL | |
| `processed_at` | TIMESTAMPTZ NOT NULL | |
| UNIQUE | `(provider, event_id)` | |

### 3.9 `feature_flags`

| Column | Type | Notes |
|--------|------|--------|
| `key` | VARCHAR(64) PK | |
| `enabled` | BOOLEAN NOT NULL | |
| `payload` | JSONB NULL | percentage rollout, allowlist telegram_ids |
| `updated_at` | TIMESTAMPTZ | |

### 3.10 `operator_memberships` (0012)

| Column | Type | Notes |
|--------|------|--------|
| `user_id` | UUID PK/FK → users RESTRICT | operator identity is an existing Telegram user |
| `role` | VARCHAR(16) | CHECK `support` or `admin` |
| `granted_by_user_id` | UUID NULL FK → users RESTRICT | granting operator, when known |
| `granted_at` | TIMESTAMPTZ | |
| `revoked_at` | TIMESTAMPTZ NULL | active membership has NULL |

Bootstrap admins are resolved server-side from `ADMIN_BOOTSTRAP_TELEGRAM_IDS`; the URL and client
state never grant a role.

### 3.11 `audit_events` (0012)

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | |
| `action_id` | UUID UNIQUE | mutation replay/idempotency identity |
| `request_hash` | CHAR(64) | detects same ID with changed payload/operator |
| `operator_user_id` | UUID FK → users RESTRICT | |
| `operator_role` | VARCHAR(16) | role at action time |
| `action` | VARCHAR(64) | bounded action code |
| `object_type` / `object_id` | VARCHAR | safe target identity |
| `before_data` / `after_data` | JSONB | explicit safe snapshots, no prompt/secrets/raw payload |
| `reason` / `reference` | VARCHAR(64) | validated safe codes |
| `correlation_id` | UUID | HTTP → audit correlation |
| `created_at` | TIMESTAMPTZ | server timestamp |

DB trigger rejects every UPDATE or DELETE. Application code only exposes append/list operations.

### 3.12 `moderation_decisions` (0013)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | decision identity |
| `user_id` | UUID FK → users CASCADE | subject identity |
| `generation_id` | UUID NULL FK → generation_jobs SET NULL | bound after a generation row is created |
| `asset_ids` | UUID[] | owned input references; never file content |
| `context` / `idempotency_key` | VARCHAR | generation/chat/prompt-assistant replay scope |
| `input_hash` | CHAR(64) | SHA-256 over text + asset IDs + context + policy version; raw text is not stored |
| `mode` / `outcome` | VARCHAR | `off/report/block` and `allow/report/block` |
| `reason_codes` | VARCHAR[] | bounded policy/technical codes |
| `policy_version` | VARCHAR | immutable decision policy |
| `provider` / `provider_model` | VARCHAR | bounded adapter metadata |
| `provider_request_id` / `error_code` | VARCHAR NULL | investigation IDs/codes; no response body |
| `review_status` / `review_outcome` | VARCHAR | operator queue state |
| `reviewed_by_user_id` / `reviewed_at` | UUID/TIMESTAMPTZ NULL | admin review identity/time |
| `created_at` | TIMESTAMPTZ | server timestamp |

UNIQUE `(user_id, context, idempotency_key)`. The table deliberately has no prompt,
image payload or raw provider-response column.

### 3.13 `user_consents` (0013)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK → users CASCADE | confirming user |
| `generation_id` | UUID NULL FK → generation_jobs SET NULL | bound to accepted generation |
| `consent_type` | VARCHAR | currently `photo_rights` |
| `policy_version` | VARCHAR | must equal current server requirement |
| `asset_ids` | UUID[] | exact source-photo scope |
| `idempotency_key` | VARCHAR | replay scope |
| `confirmed_at` | TIMESTAMPTZ | explicit confirmation time |

UNIQUE `(user_id, consent_type, idempotency_key)`; a changed asset set or policy version
under the same key is an idempotency conflict.

### 3.14 `generation_templates` and snapshots (0014)

`generation_templates` is the canonical RU/KK catalog for six image templates and five video
recipes. A stable UUID and slug identify the template; `version`, `kind`, `enabled`,
`display_order`, localized name/description and prompt preset, aspect ratio, optional duration,
compatible modalities, required-input schema, preview metadata and optional controlled compositor
are stored server-side.

`price_quotes` and `generation_jobs` receive nullable `template_id`, `template_slug`,
`template_version`, `template_inputs` and `template_snapshot`. Existing rows remain valid with
`NULL`/empty values. New template quotes and jobs preserve a full immutable JSON snapshot, so
history does not depend on a later catalog edit. PostgreSQL triggers reject changes to the five
template fields on both quote and job rows. Catalog rows are referenced with `RESTRICT`; operators
disable a template instead of deleting it.

Only the validated fields declared by `required_inputs` are accepted. Product-card and
toi-invitation text is rendered after provider completion by a deterministic compositor. The
provider never controls price/contact/date placement, and the compositor accepts no client font,
position, URL or markup.

### 3.15 Telegram Stars refunds and reconciliation (0015)

`payment_refunds` is the durable state machine for one refund per Stars charge. Order, receipt,
charge ID and operator reference are unique. The row separates external confirmation
(`external_refunded_at`) from idempotent reverse-ledger completion (`ledger_transaction_id`), so a
crash between Telegram and PostgreSQL is recoverable.

`star_transaction_observations` stores normalized transaction metadata with unique
`(telegram_transaction_id, direction)`. It intentionally omits raw Telegram responses. The same
Telegram ID may appear once as incoming purchase and once as outgoing reversal.

`payment_reconciliation_runs` records bounded run outcome/counts. `payment_reconciliation_issues`
upserts stable discrepancy keys with `open`, `needs_review` or `resolved` state. Foreign keys to an
order/refund are optional because Telegram can expose a transaction for which the local receipt is
missing.

### 3.16 Immutable image routing snapshot (0016)

`generation_jobs.routing_snapshot` stores the server-selected primary and optional fallback route,
provider model identifiers, operation/capability decision, safe cost ceiling and rollout gates at
job creation. The worker completes or recovers the job from this snapshot rather than mutable
catalog state, so an operator toggle cannot change an already-confirmed user price or introduce a
new retry loop. The migration seeds `google_image=false` and `image_fallback=false`; the Google
route supports image generation/edit only, while upscale stays primary-only.

### 3.17 Referral MVP (0017)

`referral_codes` provides at most one opaque personal code per user. `referral_attributions` stores
exactly one inviter for an invited user, rejects self-referral, uses `RESTRICT` foreign keys and is
protected by a database trigger that rejects both UPDATE and DELETE. Attribution is created only
inside the successful new-user registration path; later `/start` updates cannot replace it.

`referral_rewards` is a one-to-one state machine for an attribution and, once observed, a unique
first payment order. Valid states are `pending`, `eligible`, `credited`, `cancelled` and
`needs_review`. Bonus amounts are snapshotted as non-negative integers. Unique ledger transaction
references plus WalletService idempotency keys (`referral:<reward_id>:inviter|invitee`) prevent
double credit. A reversal before credit cancels the reward; a reversal after credit marks it for
review without an automatic negative-wallet clawback.

### 3.18 OpenAI image provider catalog gate (0018)

The additive seed migration creates the `openai_image=false` feature flag plus two disabled-by-
flag GPT Image 2 generation models. The existing immutable quote and routing snapshots remain the
authority for price and provider selection; no new job columns are required. Image editing stays
adapter-capable but has no public catalog SKU until its variable input-image costs are reconciled.

---

## 4. Relationship diagram (Mermaid)

```mermaid
erDiagram
  users ||--|| wallets : has
  users ||--o{ auth_sessions : has
  users ||--o{ generation_jobs : owns
  users ||--o{ generation_assets : owns
  users ||--o| operator_memberships : operator_role
  users ||--o{ audit_events : performs
  users ||--o{ moderation_decisions : subject
  users ||--o{ user_consents : confirms
  users ||--o{ payment_orders : buys
  users ||--o| referral_codes : owns
  users ||--o{ referral_attributions : invites
  users ||--o| referral_attributions : invited_by
  wallets ||--o{ credit_transactions : ledger
  wallets ||--o{ credit_reservations : holds
  catalog_models ||--o{ generation_jobs : priced_by
  credit_reservations ||--o| generation_jobs : binds
  generation_jobs ||--o{ generation_attempts : retries
  generation_jobs ||--o{ generation_assets : files
  generation_jobs ||--o{ provider_usage : costs
  generation_attempts ||--o{ provider_usage : attempt_cost
  generation_jobs ||--o{ webhook_receipts : callbacks
  generation_jobs ||--o{ moderation_decisions : decision
  generation_jobs ||--o{ user_consents : consent
  generation_templates ||--o{ generation_jobs : snapshotted_by
  generation_templates ||--o{ price_quotes : quoted_by
  payment_orders ||--o| payment_receipts : confirmed_by
  payment_orders ||--o| payment_refunds : refunded_by
  payment_refunds ||--o{ payment_reconciliation_issues : investigated_by
  referral_codes ||--o{ referral_attributions : attributes
  referral_attributions ||--|| referral_rewards : rewards
  payment_orders ||--o| referral_rewards : qualifies
  credit_transactions ||--o| referral_rewards : credits
```

---

## 5. Integer money rules

1. All user-facing amounts: **integer credit units** (`INT`).
2. All provider costs: **integer** in a fixed subunit (`provider_cost_units`), never `float`/`Numeric` for money paths.
3. Pricing multipliers in `pricing_rules` are integer factors or rational pairs `(num, den)` stored as ints; final price computed with integer arithmetic and explicit rounding mode (ceil to user).
4. DB CHECKs enforce `balance >= 0`, `reserved >= 0`, `balance >= reserved`, positive prices.

---

## 6. Retention & GC

| Class | Default policy (config) |
|-------|-------------------------|
| `temp_input` | delete object + soft-delete row after 24–72h if unused / after job terminal + grace |
| `permanent_output` | retain while account active; soft-delete on user delete request |
| `auth_sessions` | purge expired/revoked daily |
| `webhook_receipts` | retain 30 days |
| `credit_reservations` held past `expires_at` | sweeper → `expired` + release reserved |

---

## 7. Migration plan (schema only)

| Rev | Contents |
|-----|----------|
| `0001_initial` | **DO NOT MODIFY** — users, wallets, credit_transactions |
| `0002_wallet_reserved` | `wallets.reserved` + CHECKs; minimal `credit_reservations` (generation_id nullable, no FK yet) |
| `0003_auth_sessions` | `auth_sessions` |
| `0004_catalog` | `catalog_models`, `price_quotes`, `feature_flags` + seed |
| `0005_assets` | `generation_assets` |
| `0006_generations` | generation jobs/attempts/provider usage/webhook receipts |
| `0007_catalog_ui_flags` | catalog UI metadata and gates |
| `0008_assistant_notifications` | prompt assistant requests and notification outbox |
| `0009_studio_operations` | generation operation metadata |
| `0010_video_mvp` | video lifecycle/provider fields |
| `0011_telegram_stars_payments` | products, orders and durable receipts |
| `0012_admin_operator_audit` | operator RBAC, user block state, append-only audit |
| `0013_moderation_consent` | privacy-safe moderation decisions, operator review state and versioned photo consent |
| `0014_generation_templates` | canonical RU/KK templates, immutable quote/job snapshots and controlled compositor metadata |
| `0015_stars_refunds` | recoverable Stars refunds, normalized transaction observations, reconciliation runs/issues |
| `0016_image_fallback` | immutable generation routing snapshot, opt-in Google image route and fallback catalog controls |
| `0017_referral_mvp` | personal codes, immutable new-user attribution and ledger-backed referral reward states |
| `0018_openai_image_provider` | disabled-by-default OpenAI GPT Image 2 catalog candidates and feature flag |

> The migration chain is additive; do not rewrite older applied revisions.
