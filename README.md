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

### Full stack

```bash
docker compose up --build
```

Health: `GET http://localhost:8000/health`

> Note: Compose maps Postgres to host port **5433** to avoid clashing with a local Postgres on 5432. Inside the Docker network services still use `postgres:5432`.

## Architecture

- `apps/bot` — Telegram handlers (thin), keyboards, middlewares
- `apps/api` — FastAPI (`/health` in iteration 1)
- `packages/kelbet` — models, repositories, services, i18n
- Wallet balance is a cache; `credit_transactions` is the immutable ledger
- Welcome bonus: 5 credits once via idempotency key `welcome:{user_id}`

## Quality

```bash
ruff check .
ruff format .
mypy
pytest
```
