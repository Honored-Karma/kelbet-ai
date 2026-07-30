import json
from pathlib import Path

from apps.worker.bundle import WORKER_TARGETS

from kelbet.config import Settings, normalize_async_database_url

ROOT = Path(__file__).resolve().parents[1]


def test_railway_postgres_url_is_normalized_for_async_sqlalchemy() -> None:
    raw = "postgresql://user:pass@postgres.railway.internal:5432/railway"
    assert normalize_async_database_url(raw) == (
        "postgresql+asyncpg://user:pass@postgres.railway.internal:5432/railway"
    )
    assert Settings(database_url=raw).database_url.startswith("postgresql+asyncpg://")


def test_existing_async_database_url_is_unchanged() -> None:
    raw = "postgresql+asyncpg://user:pass@localhost:5433/kelbet"
    assert normalize_async_database_url(raw) == raw


def test_deployment_json_files_are_valid_and_target_expected_commands() -> None:
    api = json.loads((ROOT / "deploy/railway/api.json").read_text(encoding="utf-8"))
    bot = json.loads((ROOT / "deploy/railway/bot.json").read_text(encoding="utf-8"))
    worker = json.loads((ROOT / "deploy/railway/worker.json").read_text(encoding="utf-8"))
    vercel = json.loads((ROOT / "apps/web/vercel.json").read_text(encoding="utf-8"))

    assert api["deploy"]["startCommand"] == "python -m apps.api"
    assert api["deploy"]["preDeployCommand"] == ["alembic upgrade head"]
    assert api["deploy"]["healthcheckPath"] == "/health"
    assert bot["deploy"]["startCommand"] == "python -m apps.bot"
    assert worker["deploy"]["startCommand"] == "python -m apps.worker.bundle"
    assert vercel["outputDirectory"] == "dist"
    assert vercel["rewrites"][0]["destination"] == "/index.html"


def test_worker_bundle_covers_every_production_queue() -> None:
    assert WORKER_TARGETS == (
        "apps.worker.main.ImageWorkerSettings",
        "apps.worker.main.TextWorkerSettings",
        "apps.worker.main.VideoWorkerSettings",
        "apps.worker.main.MaintainWorkerSettings",
    )
