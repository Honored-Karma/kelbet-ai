"""Stuck sweeper: timed_out + release for abandoned submitting/running jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings
from kelbet.db.models.catalog import CatalogModel
from kelbet.db.models.credit_reservation import CreditReservation
from kelbet.db.models.generation import GenerationJob
from kelbet.domain.enums import GenerationStatus, Language, Plan, ReservationStatus, TxReason
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.stuck_sweeper import StuckSweeper
from kelbet.services.wallet import WalletService


@pytest.mark.asyncio
async def test_stuck_sweeper_times_out_running_and_releases(
    session: AsyncSession,
) -> None:
    await seed_catalog(session)
    model = (
        await session.execute(select(CatalogModel).where(CatalogModel.slug == "mock-image"))
    ).scalar_one()

    user = await UserRepository(session).create(
        telegram_id=920001,
        username="stuck_user",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await WalletRepository(session).create(user.id)
    await WalletService(session).credit(wallet.id, 50, TxReason.WELCOME_BONUS, f"welcome:{user.id}")
    reservation = await WalletService(session).reserve(
        wallet.id,
        5,
        f"reserve:gen:stuck-{user.id}",
        user_id=user.id,
        quote_snapshot={"model_slug": "mock-image"},
    )
    started = datetime.now(UTC) - timedelta(seconds=900)
    job = GenerationJob(
        id=uuid4(),
        user_id=user.id,
        model_id=model.id,
        modality="image",
        status=GenerationStatus.RUNNING.value,
        idempotency_key="stuck-1",
        request_hash="abc",
        prompt_redacted=True,
        params={},
        reservation_id=reservation.reservation_id,
        user_credit_price=5,
        provider="mock",
        provider_model_id="mock-image-v1",
        provider_job_id="task-stuck",
        progress_pct=40,
        progress_stage="running",
        attempt_count=1,
        max_attempts=3,
        queued_at=started,
        started_at=started,
        next_poll_at=datetime.now(UTC) + timedelta(hours=1),
        correlation_id=uuid4(),
        prompt="x",
    )
    session.add(job)
    await session.flush()

    settings = Settings(runway_image_timeout_seconds=600, stuck_submitting_seconds=180)
    swept = await StuckSweeper(session, settings).sweep(now=datetime.now(UTC))
    assert job.id in swept
    assert job.status == GenerationStatus.TIMED_OUT.value
    assert job.error_code == "stuck_timeout"
    assert job.next_poll_at is None

    refreshed = await WalletRepository(session).get_by_id(wallet.id)
    assert refreshed is not None
    assert refreshed.balance == 50
    assert refreshed.reserved == 0
    res = (
        await session.execute(
            select(CreditReservation).where(CreditReservation.id == reservation.reservation_id)
        )
    ).scalar_one()
    assert res.status == ReservationStatus.RELEASED.value
