"""Reservation sweeper: return holds nothing else will finalise, and only those."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings
from kelbet.db.models.catalog import CatalogModel
from kelbet.db.models.credit_reservation import CreditReservation
from kelbet.db.models.generation import GenerationJob
from kelbet.db.models.user import User
from kelbet.db.models.wallet import Wallet
from kelbet.domain.enums import GenerationStatus, Language, Plan, ReservationStatus, TxReason
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.reservation_sweeper import ReservationSweeper
from kelbet.services.video_workflow import (
    EXTENDED_WORKFLOW_TYPE,
    is_extended_workflow,
    job_timeout_seconds,
)
from kelbet.services.wallet import (
    DEFAULT_RESERVATION_TTL,
    ReservationResult,
    WalletService,
)

_TELEGRAM_ID = iter(range(940_001, 940_999))


async def _user_with_wallet(session: AsyncSession, *, credits: int = 100) -> tuple[User, Wallet]:
    user = await UserRepository(session).create(
        telegram_id=next(_TELEGRAM_ID),
        username="res_sweep",
        language=Language.RU,
        plan=Plan.FREE,
    )
    wallet = await WalletRepository(session).create(user.id)
    await WalletService(session).credit(
        wallet.id, credits, TxReason.WELCOME_BONUS, f"welcome:{user.id}"
    )
    return user, wallet


async def _hold(
    session: AsyncSession,
    user: User,
    wallet: Wallet,
    *,
    amount: int = 5,
    held_at: datetime,
    ttl: timedelta = DEFAULT_RESERVATION_TTL,
) -> ReservationResult:
    return await WalletService(session).reserve(
        wallet.id,
        amount,
        f"reserve:gen:{uuid4()}",
        user_id=user.id,
        quote_snapshot={"model_slug": "mock-image"},
        ttl=ttl,
        now=held_at,
    )


async def _job(
    session: AsyncSession,
    user: User,
    *,
    status: GenerationStatus,
    reservation_id: UUID,
    created_at: datetime,
    link_reservation: bool = True,
) -> GenerationJob:
    await seed_catalog(session)
    model = (
        await session.execute(select(CatalogModel).where(CatalogModel.slug == "mock-image"))
    ).scalar_one()
    job = GenerationJob(
        id=uuid4(),
        user_id=user.id,
        model_id=model.id,
        modality="image",
        status=status.value,
        idempotency_key=f"res-sweep-{uuid4()}",
        request_hash="abc",
        prompt_redacted=True,
        params={},
        reservation_id=reservation_id,
        user_credit_price=5,
        provider="mock",
        provider_model_id="mock-image-v1",
        progress_pct=0,
        progress_stage=status.value,
        attempt_count=0,
        max_attempts=3,
        queued_at=created_at,
        correlation_id=uuid4(),
        prompt="x",
    )
    session.add(job)
    await session.flush()
    if link_reservation:
        # Production writes both sides of the link together; mirror that by default.
        (await _reservation(session, reservation_id)).generation_id = job.id
        await session.flush()
    return job


async def _reservation(session: AsyncSession, reservation_id: UUID) -> CreditReservation:
    return (
        await session.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_expires_hold_that_was_never_bound_to_a_generation(
    session: AsyncSession,
) -> None:
    """Reserved, then the request died before linking a job. Nothing will ever finalise it."""

    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(minutes=5)
    reservation = await _hold(session, user, wallet, amount=7, held_at=long_ago)

    before = await WalletRepository(session).get_by_id(wallet.id)
    assert before is not None
    assert before.reserved == 7

    expired = await ReservationSweeper(session).sweep(now=datetime.now(UTC))

    assert reservation.reservation_id in expired
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.EXPIRED.value
    assert row.finalized_at is not None
    after = await WalletRepository(session).get_by_id(wallet.id)
    assert after is not None
    assert after.reserved == 0
    # The hold is returned, not charged: the balance never moved.
    assert after.balance == 100


@pytest.mark.asyncio
async def test_leaves_hold_of_a_live_generation_alone(session: AsyncSession) -> None:
    """The guard that matters: releasing under running work would give the job away free."""

    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(hours=1)
    reservation = await _hold(session, user, wallet, held_at=long_ago)
    await _job(
        session,
        user,
        status=GenerationStatus.RUNNING,
        reservation_id=reservation.reservation_id,
        created_at=long_ago,
    )

    expired = await ReservationSweeper(session).sweep(now=datetime.now(UTC))

    assert expired == []
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.HELD.value
    wallet_row = await WalletRepository(session).get_by_id(wallet.id)
    assert wallet_row is not None
    assert wallet_row.reserved == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        GenerationStatus.CREATED,
        GenerationStatus.QUEUED,
        GenerationStatus.SUBMITTING,
        GenerationStatus.RUNNING,
        GenerationStatus.FINALIZING,
    ],
)
async def test_every_active_status_is_protected(
    session: AsyncSession, status: GenerationStatus
) -> None:
    """Protection is derived from the transition table, so assert the whole active set."""

    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(hours=1)
    reservation = await _hold(session, user, wallet, held_at=long_ago)
    await _job(
        session,
        user,
        status=status,
        reservation_id=reservation.reservation_id,
        created_at=long_ago,
    )

    assert await ReservationSweeper(session).sweep(now=datetime.now(UTC)) == []
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.HELD.value


@pytest.mark.asyncio
async def test_protects_a_live_job_when_only_the_job_side_of_the_link_was_written(
    session: AsyncSession,
) -> None:
    """A half-written link must not read as an abandoned hold.

    The reservation names no generation, but a running job names the reservation.
    Deciding from the reservation's column alone would hand a live job's credits
    back and let its output come out free.
    """

    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(hours=1)
    reservation = await _hold(session, user, wallet, held_at=long_ago)
    await _job(
        session,
        user,
        status=GenerationStatus.RUNNING,
        reservation_id=reservation.reservation_id,
        created_at=long_ago,
        link_reservation=False,
    )

    row = await _reservation(session, reservation.reservation_id)
    assert row.generation_id is None, "guard: this test is about the unlinked reservation"

    assert await ReservationSweeper(session).sweep(now=datetime.now(UTC)) == []
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.HELD.value


@pytest.mark.asyncio
async def test_expires_hold_left_behind_by_a_terminal_generation(
    session: AsyncSession,
) -> None:
    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(minutes=1)
    reservation = await _hold(session, user, wallet, held_at=long_ago)
    await _job(
        session,
        user,
        status=GenerationStatus.FAILED,
        reservation_id=reservation.reservation_id,
        created_at=long_ago,
    )

    assert reservation.reservation_id in await ReservationSweeper(session).sweep(
        now=datetime.now(UTC)
    )
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.EXPIRED.value
    wallet_row = await WalletRepository(session).get_by_id(wallet.id)
    assert wallet_row is not None
    assert wallet_row.reserved == 0


@pytest.mark.asyncio
async def test_ignores_holds_before_their_deadline(session: AsyncSession) -> None:
    user, wallet = await _user_with_wallet(session)
    reservation = await _hold(session, user, wallet, held_at=datetime.now(UTC))

    assert await ReservationSweeper(session).sweep(now=datetime.now(UTC)) == []
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.HELD.value


@pytest.mark.asyncio
async def test_sweeping_twice_returns_the_credits_once(session: AsyncSession) -> None:
    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(minutes=5)
    reservation = await _hold(session, user, wallet, amount=9, held_at=long_ago)

    first = await ReservationSweeper(session).sweep(now=datetime.now(UTC))
    second = await ReservationSweeper(session).sweep(now=datetime.now(UTC))

    assert reservation.reservation_id in first
    assert second == []
    wallet_row = await WalletRepository(session).get_by_id(wallet.id)
    assert wallet_row is not None
    assert wallet_row.reserved == 0
    assert wallet_row.balance == 100


@pytest.mark.asyncio
async def test_captured_hold_is_never_expired(session: AsyncSession) -> None:
    """A captured hold is paid work. It must stay out of the sweeper's candidate set."""

    user, wallet = await _user_with_wallet(session)
    long_ago = datetime.now(UTC) - DEFAULT_RESERVATION_TTL - timedelta(minutes=5)
    reservation = await _hold(session, user, wallet, amount=6, held_at=long_ago)
    await WalletService(session).capture(reservation.reservation_id)

    assert await ReservationSweeper(session).sweep(now=datetime.now(UTC)) == []
    row = await _reservation(session, reservation.reservation_id)
    assert row.status == ReservationStatus.CAPTURED.value
    wallet_row = await WalletRepository(session).get_by_id(wallet.id)
    assert wallet_row is not None
    assert wallet_row.balance == 94


def test_reservation_ttl_outlasts_the_longest_job_budget() -> None:
    """The expiry may never fall due while a legitimate job could still be running.

    Extended Veo work is the longest budget in the system and previously matched
    the reservation TTL exactly, which would have let expiry race a live job.
    """

    settings = Settings()
    extended = GenerationJob(
        modality="video",
        params={"duration_sec": 29},
        routing_snapshot={"workflow": {"type": EXTENDED_WORKFLOW_TYPE}},
    )
    assert is_extended_workflow(extended), "guard: this job must exercise the extended budget"

    longest_budget = max(
        job_timeout_seconds(settings, extended),
        settings.veo_extended_total_timeout_seconds,
        settings.runway_video_timeout_seconds,
    )
    assert DEFAULT_RESERVATION_TTL.total_seconds() > longest_budget
