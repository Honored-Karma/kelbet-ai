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


@pytest.mark.asyncio
async def test_stuck_sweeper_times_out_a_job_no_worker_ever_claimed(
    session: AsyncSession,
) -> None:
    """A lost queue message used to strand the hold and a concurrency slot forever.

    Nothing moved a queued job on except a worker claiming it, and the sweeper only
    looked at jobs that had already reached a provider, so a dropped message left
    the user permanently short on `available` with no recovery path.
    """

    await seed_catalog(session)
    model = (
        await session.execute(select(CatalogModel).where(CatalogModel.slug == "mock-image"))
    ).scalar_one()

    user = await UserRepository(session).create(
        telegram_id=920002,
        username="unclaimed_user",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await WalletRepository(session).create(user.id)
    await WalletService(session).credit(wallet.id, 50, TxReason.WELCOME_BONUS, f"welcome:{user.id}")
    reservation = await WalletService(session).reserve(
        wallet.id,
        5,
        f"reserve:gen:unclaimed-{user.id}",
        user_id=user.id,
        quote_snapshot={"model_slug": "mock-image"},
    )
    queued = datetime.now(UTC) - timedelta(seconds=1200)
    job = GenerationJob(
        id=uuid4(),
        user_id=user.id,
        model_id=model.id,
        modality="image",
        status=GenerationStatus.QUEUED.value,
        idempotency_key="unclaimed-1",
        request_hash="abc",
        prompt_redacted=True,
        params={},
        reservation_id=reservation.reservation_id,
        user_credit_price=5,
        provider="mock",
        provider_model_id="mock-image-v1",
        provider_job_id=None,
        progress_pct=0,
        progress_stage="queued",
        attempt_count=0,
        max_attempts=3,
        queued_at=queued,
        started_at=None,
        correlation_id=uuid4(),
        prompt="x",
    )
    session.add(job)
    await session.flush()

    settings = Settings(stuck_queued_seconds=900)
    swept = await StuckSweeper(session, settings).sweep(now=datetime.now(UTC))

    assert job.id in swept
    assert job.status == GenerationStatus.TIMED_OUT.value
    # Named apart from a provider timeout: this code means the queue dropped work.
    assert job.error_code == "stuck_unclaimed"

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


@pytest.mark.asyncio
async def test_stuck_sweeper_leaves_a_freshly_queued_job_alone(session: AsyncSession) -> None:
    """A queue with a backlog is normal; only a long-unclaimed job is a fault."""

    await seed_catalog(session)
    model = (
        await session.execute(select(CatalogModel).where(CatalogModel.slug == "mock-image"))
    ).scalar_one()

    user = await UserRepository(session).create(
        telegram_id=920003,
        username="fresh_queue_user",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await WalletRepository(session).create(user.id)
    await WalletService(session).credit(wallet.id, 50, TxReason.WELCOME_BONUS, f"welcome:{user.id}")
    reservation = await WalletService(session).reserve(
        wallet.id,
        5,
        f"reserve:gen:fresh-{user.id}",
        user_id=user.id,
        quote_snapshot={"model_slug": "mock-image"},
    )
    queued = datetime.now(UTC) - timedelta(seconds=30)
    job = GenerationJob(
        id=uuid4(),
        user_id=user.id,
        model_id=model.id,
        modality="image",
        status=GenerationStatus.QUEUED.value,
        idempotency_key="fresh-1",
        request_hash="abc",
        prompt_redacted=True,
        params={},
        reservation_id=reservation.reservation_id,
        user_credit_price=5,
        provider="mock",
        provider_model_id="mock-image-v1",
        progress_pct=0,
        progress_stage="queued",
        attempt_count=0,
        max_attempts=3,
        queued_at=queued,
        correlation_id=uuid4(),
        prompt="x",
    )
    session.add(job)
    await session.flush()

    settings = Settings(stuck_queued_seconds=900)
    swept = await StuckSweeper(session, settings).sweep(now=datetime.now(UTC))

    assert swept == []
    assert job.status == GenerationStatus.QUEUED.value
    refreshed = await WalletRepository(session).get_by_id(wallet.id)
    assert refreshed is not None
    assert refreshed.reserved == 5
