# KELBET AI

Bilingual Telegram AI service for Kazakhstan (RU / KK). Modular monolith: Telegram bot + FastAPI + shared domain package.

## Stack

- Python 3.12, aiogram 3, FastAPI
- PostgreSQL, SQLAlchemy 2 async, Alembic
- Redis, Pydantic Settings, Docker Compose
- pytest, Ruff, mypy

## Quick start

```bash
cp .env.example .env
# set BOT_TOKEN in .env

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev]"

docker compose up -d postgres redis
# create test DB (once):
docker compose exec postgres psql -U kelbet -c "CREATE DATABASE kelbet_test;"

# Host apps connect via mapped port 5433 (see .env.example)
alembic upgrade head
pytest
```

### Run API

```bash
python -m apps.api
```

### Run bot

```bash
python -m apps.bot
```

Set `MINI_APP_URL` to the public HTTPS URL of the Mini App. When configured,
the bot opens `/create` and `/history` directly from its reply keyboard.
Set `SUPPORT_USERNAME` without `@` to enable `/support` and `/paysupport`.

Bot commands:

- `/create` — open the creation studio
- `/history` — open previous generations
- `/balance` — show total, reserved, and available credits
- `/profile` — show the Telegram profile
- `/settings` — change interface language
- `/support` and `/paysupport` — contact support

### Run Mini App

```bash
cd apps/web
npm install
npm run dev
```

Default `VITE_API_MODE=mock` exercises UI without the backend. For live API set `VITE_API_MODE=live` and `VITE_API_BASE_URL=http://localhost:8000`.

### Full stack

```bash
docker compose up --build
```

Health: `GET http://localhost:8000/health`

> Note: Compose maps Postgres to host port **5433** to avoid clashing with a local Postgres on 5432. Inside the Docker network services still use `postgres:5432`.

## Architecture

- `apps/bot` — Telegram handlers (thin), keyboards, middlewares
- `apps/api` — FastAPI (`/health`; v0.3 expands `/api/v1`)
- `apps/worker` — generation runner, recovery sweeper, and durable Telegram notification dispatcher
- `apps/web` — Telegram Mini App (Vite + React)
- `packages/kelbet` — models, repositories, services, i18n
- Wallet balance is a cache; `credit_transactions` is the immutable ledger
- Soft-hold: `wallets.reserved`; `available = balance - reserved`
- Welcome bonus: 60 credits once via idempotency key `welcome:{user_id}`
- AI chat: `ChatService` + `ChatProvider` (`mock` / `openrouter`); debit `chat:{request_id}` after successful reply
- Prompt Lab: localized RU/KK image-prompt improvement with successful-result billing and idempotent replay
- Visual history: secure batch preview URLs for the current user's generation archive
- Ready notifications: transactional outbox with retry/backoff and a per-user Telegram preference
- Studio operations: catalog-driven Create/Edit/Upscale, Smart/Fast/Quality presets, and up to 10 ordered references
- Video Studio: text/photo-to-video, Fast/Quality, Runway primary routes, and a cost-bounded Google Veo fallback
- Video completion: signed Google callbacks plus provider-safe Runway polling
- Image providers: opt-in Google and OpenAI GPT Image 2 routes, each disabled until its own canary
- Video production gate: machine-readable 100-job lifecycle and financial reconciliation
- Telegram Stars: gated XTR invoices, validated checkout, durable update intake/receipts, replay,
  and idempotent credit delivery
- Stars subscriptions: recurring Telegram-native billing and idempotent period grants; API/bot/worker
  are implemented, while the Mini App and production rollout remain disabled

See `docs/architecture/KELBET_V03_PLAN.md` for the approved v0.3 plan.
See `docs/architecture/STUDIO_VIDEO_OPERATIONS.md` for the Video MVP provider,
fallback, and financial contracts.
See `docs/architecture/VIDEO_PRODUCTION_GATE.md` for signed callback setup and
the required 100-job staging gate.
See `docs/architecture/TELEGRAM_STARS_PAYMENTS.md` for the payment contract and
remaining legal, refund, and reconciliation gates.
See `docs/architecture/OPENAI_IMAGE_PROVIDER_RUNBOOK.md` for the disabled-by-default
GPT Image 2 rollout and rollback procedure.

## Deployment

Production deployment files are included for:

- Vercel: `apps/web/vercel.json`
- Railway API: `deploy/railway/api.json`
- Railway bot: `deploy/railway/bot.json`
- Railway bundled workers: `deploy/railway/worker.json`

Russian step-by-step guide:
`docs/DEPLOY_VERCEL_RAILWAY_RU.md`.

## Quality

```bash
ruff check .
ruff format .
mypy
pytest
```
