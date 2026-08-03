"""Telegram-billed subscription lifecycle against a live Postgres.

The tests that matter are the ones about money arriving more than once, and the one that
pins down the property the previous design got wrong: **the expiry sweep must never grant
credits**. Renewal is a consequence of a charge, not of a date.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import CreditTransaction, SubscriptionGrant, UserSubscription, Wallet
from kelbet.domain.enums import Language, Plan, SubscriptionStatus, TxReason
from kelbet.domain.exceptions import PaymentUnavailableError
from kelbet.repositories.user import UserRepository
from kelbet.services.registration import RegistrationService
from kelbet.services.subscription import (
    SubscriptionService,
    SubscriptionValidationError,
    is_subscription_payload,
    process_due_subscriptions,
)
from kelbet.subscriptions import seed_subscription_plans
from kelbet.subscriptions.seeds import subscription_plan_rows

WELCOME = 60
PRO = next(row for row in subscription_plan_rows() if row["slug"] == "pro")
START = next(row for row in subscription_plan_rows() if row["slug"] == "start")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "subscriptions_enabled": True,
        "payments_enabled": True,
        "payment_terms_url": "https://kelbet.ai/terms",
        "payment_refund_policy_url": "https://kelbet.ai/refunds",
        "payment_terms_version": "test-v1",
        "payment_seller_identity": "KELBET TEST SELLER",
        "payment_finance_review_confirmed": True,
        "support_username": "kelbet_support",
        "welcome_credits": WELCOME,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _register(session: AsyncSession, telegram_id: int) -> UUID:
    user, _ = await RegistrationService(
        session, Settings(welcome_credits=WELCOME)
    ).register_with_language(
        telegram_id=telegram_id,
        username=f"sub_{telegram_id}",
        language=Language.RU,
    )
    return user.id


async def _balance(session: AsyncSession, user_id: UUID) -> int:
    return int(
        (
            await session.execute(select(Wallet.balance).where(Wallet.user_id == user_id))
        ).scalar_one()
    )


async def _plan_of(session: AsyncSession, user_id: UUID) -> str:
    user = await UserRepository(session).get_by_id(user_id)
    assert user is not None
    return user.plan


async def _checkout(
    session: AsyncSession, user_id: UUID, *, slug: str = "pro", settings: Settings | None = None
) -> str:
    checkout = await SubscriptionService(session, settings or _settings()).start_checkout(
        user_id,
        slug,
        language=Language.RU,
        terms_accepted=True,
        accepted_terms_version="test-v1",
    )
    return checkout.invoice_payload


async def _charge(
    session: AsyncSession,
    *,
    telegram_id: int,
    payload: str,
    charge_id: str,
    expires_at: datetime,
    stars: int | None = None,
    settings: Settings | None = None,
) -> object:
    return await SubscriptionService(session, settings or _settings()).apply_charge(
        telegram_id=telegram_id,
        invoice_payload=payload,
        currency="XTR",
        total_amount=stars if stars is not None else int(PRO["stars"]),
        charge_id=charge_id,
        expires_at=expires_at,
    )


# --------------------------------------------------------------------------- routing


def test_payload_prefix_separates_subscriptions_from_packs() -> None:
    """The handlers route on the payload alone, so the prefixes must not overlap."""
    assert is_subscription_payload("kelbet-sub:abc")
    assert not is_subscription_payload("kelbet:abc")
    assert not is_subscription_payload("")


# -------------------------------------------------------------------------- checkout


@pytest.mark.asyncio
async def test_checkout_is_gated_and_grants_nothing(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_001)

    with pytest.raises(PaymentUnavailableError):
        await SubscriptionService(session, _settings(subscriptions_enabled=False)).start_checkout(
            user_id,
            "pro",
            language=Language.RU,
            terms_accepted=True,
            accepted_terms_version="test-v1",
        )

    payload = await _checkout(session, user_id)
    assert is_subscription_payload(payload)
    subscription = (await session.execute(select(UserSubscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.PENDING.value
    # An intent, not a payment: no grant, no credits, still on free.
    assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 0
    assert await _balance(session, user_id) == WELCOME
    assert await _plan_of(session, user_id) == Plan.FREE.value


@pytest.mark.asyncio
async def test_repeated_checkout_reuses_the_pending_payload(session: AsyncSession) -> None:
    """Two taps must not leave the user with two invoice links that both bill."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_002)
    first = await _checkout(session, user_id)
    second = await _checkout(session, user_id)
    assert first == second
    assert await session.scalar(select(func.count()).select_from(UserSubscription)) == 1


@pytest.mark.asyncio
async def test_switching_plans_requires_cancelling_first(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_003)
    payload = await _checkout(session, user_id)
    await _charge(
        session,
        telegram_id=960_003,
        payload=payload,
        charge_id="sw-1",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    with pytest.raises(SubscriptionValidationError, match="Cancel the current subscription"):
        await _checkout(session, user_id, slug="start")


@pytest.mark.asyncio
async def test_stale_terms_are_rejected(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_004)
    service = SubscriptionService(session, _settings())
    with pytest.raises(SubscriptionValidationError, match="Terms must be accepted"):
        await service.start_checkout(
            user_id,
            "pro",
            language=Language.RU,
            terms_accepted=False,
            accepted_terms_version="test-v1",
        )
    with pytest.raises(SubscriptionValidationError, match="no longer current"):
        await service.start_checkout(
            user_id, "pro", language=Language.RU, terms_accepted=True, accepted_terms_version="old"
        )


# ----------------------------------------------------------------------------- money


@pytest.mark.asyncio
async def test_first_charge_activates_and_grants_one_period(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_010)
    payload = await _checkout(session, user_id)
    expires = datetime.now(UTC) + timedelta(days=30)

    outcome = await _charge(
        session, telegram_id=960_010, payload=payload, charge_id="ch-1", expires_at=expires
    )

    assert outcome.applied is True  # type: ignore[attr-defined]
    assert outcome.is_first is True  # type: ignore[attr-defined]
    assert outcome.credits == int(PRO["credits_per_period"])  # type: ignore[attr-defined]
    assert await _balance(session, user_id) == WELCOME + int(PRO["credits_per_period"])
    assert await _plan_of(session, user_id) == Plan.PRO.value

    subscription = (await session.execute(select(UserSubscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    # Telegram's date, not a locally computed one.
    assert subscription.current_period_end == expires
    assert subscription.current_period_index == 0
    # Kept because editUserStarSubscription addresses the subscription by it.
    assert subscription.root_charge_id == "ch-1"


@pytest.mark.asyncio
async def test_redelivered_charge_grants_exactly_once(session: AsyncSession) -> None:
    """Telegram retries updates. The same charge id must never pay out twice."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_011)
    payload = await _checkout(session, user_id)
    expires = datetime.now(UTC) + timedelta(days=30)

    first = await _charge(
        session, telegram_id=960_011, payload=payload, charge_id="ch-replay", expires_at=expires
    )
    second = await _charge(
        session, telegram_id=960_011, payload=payload, charge_id="ch-replay", expires_at=expires
    )

    assert first.applied is True  # type: ignore[attr-defined]
    assert second.applied is False  # type: ignore[attr-defined]
    # A replay still reports the period's credits, so the user gets a correct message.
    assert second.credits == int(PRO["credits_per_period"])  # type: ignore[attr-defined]
    assert await _balance(session, user_id) == WELCOME + int(PRO["credits_per_period"])
    assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 1
    grants = await session.scalar(
        select(func.count())
        .select_from(CreditTransaction)
        .where(CreditTransaction.reason == TxReason.PLAN_GRANT.value)
    )
    assert grants == 1


@pytest.mark.asyncio
async def test_concurrent_delivery_of_one_charge_grants_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two workers handed the same charge at once. The row lock and the unique charge id
    must collapse them into a single grant."""
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 960_012)
        payload = await _checkout(session, user_id)
    expires = datetime.now(UTC) + timedelta(days=30)

    async def deliver() -> bool:
        async with session_factory() as session, session.begin():
            outcome = await _charge(
                session,
                telegram_id=960_012,
                payload=payload,
                charge_id="ch-concurrent",
                expires_at=expires,
            )
            return bool(outcome.applied)  # type: ignore[attr-defined]

    assert sorted(await asyncio.gather(deliver(), deliver())) == [False, True]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 1
        assert await _balance(session, user_id) == WELCOME + int(PRO["credits_per_period"])


@pytest.mark.asyncio
async def test_renewal_grants_another_period_and_extends_the_deadline(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_013)
    payload = await _checkout(session, user_id)
    first_end = datetime.now(UTC) + timedelta(days=30)
    second_end = first_end + timedelta(days=30)

    await _charge(
        session, telegram_id=960_013, payload=payload, charge_id="rn-1", expires_at=first_end
    )
    # A renewal reuses the original payload with a new charge id — exactly the case the
    # one-off payment_orders path would have rejected as a duplicate charge.
    renewal = await _charge(
        session, telegram_id=960_013, payload=payload, charge_id="rn-2", expires_at=second_end
    )

    assert renewal.applied is True  # type: ignore[attr-defined]
    assert renewal.is_first is False  # type: ignore[attr-defined]
    assert await _balance(session, user_id) == WELCOME + 2 * int(PRO["credits_per_period"])
    subscription = (await session.execute(select(UserSubscription))).scalar_one()
    assert subscription.current_period_index == 1
    assert subscription.current_period_end == second_end
    assert subscription.root_charge_id == "rn-1"
    assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 2


@pytest.mark.asyncio
async def test_wrong_amount_wrong_buyer_and_unknown_payload_grant_nothing(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_014)
    payload = await _checkout(session, user_id)
    expires = datetime.now(UTC) + timedelta(days=30)

    underpaid = await _charge(
        session,
        telegram_id=960_014,
        payload=payload,
        charge_id="bad-amount",
        expires_at=expires,
        stars=int(PRO["stars"]) - 1,
    )
    other_buyer = await _charge(
        session, telegram_id=999_999, payload=payload, charge_id="bad-buyer", expires_at=expires
    )
    unknown = await _charge(
        session,
        telegram_id=960_014,
        payload="kelbet-sub:nope",
        charge_id="bad-payload",
        expires_at=expires,
    )

    assert underpaid.error_code == "amount_mismatch"  # type: ignore[attr-defined]
    assert other_buyer.error_code == "buyer_mismatch"  # type: ignore[attr-defined]
    assert unknown.error_code == "subscription_not_found"  # type: ignore[attr-defined]
    assert await _balance(session, user_id) == WELCOME
    assert await _plan_of(session, user_id) == Plan.FREE.value
    assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 0


# ------------------------------------------------------------- the hole that was closed


@pytest.mark.asyncio
async def test_the_expiry_sweep_never_grants_credits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The property the previous design got wrong.

    Renewal used to be driven by a local clock: `process_due` advanced the period and
    credited it, so a subscriber would have received credits every 30 days for ever off a
    single payment. The sweep must expire and nothing else.
    """
    expires = datetime.now(UTC) + timedelta(days=30)
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 960_020)
        payload = await _checkout(session, user_id)
        await _charge(
            session, telegram_id=960_020, payload=payload, charge_id="hole-1", expires_at=expires
        )
        paid_balance = await _balance(session, user_id)

    settings = _settings()
    # Before the deadline: nothing happens at all.
    assert (
        await process_due_subscriptions(
            session_factory, settings, now=expires - timedelta(seconds=1)
        )
        == 0
    )
    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.PRO.value

    # After the deadline, and again well past it: expired once, credited never.
    assert await process_due_subscriptions(session_factory, settings, now=expires) == 1
    assert (
        await process_due_subscriptions(
            session_factory, settings, now=expires + timedelta(days=120)
        )
        == 0
    )

    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.FREE.value
        subscription = (await session.execute(select(UserSubscription))).scalar_one()
        assert subscription.status == SubscriptionStatus.EXPIRED.value
        # Exactly one grant, from the one charge. Credits already given stay the user's.
        assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == 1
        assert await _balance(session, user_id) == paid_balance


@pytest.mark.asyncio
async def test_two_concurrent_workers_expire_each_subscription_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """SKIP LOCKED is what makes this safe: the second worker must skip rows the first
    holds rather than block or act twice."""
    expires = datetime.now(UTC) + timedelta(days=30)
    telegram_ids = [960_030 + index for index in range(6)]
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        for telegram_id in telegram_ids:
            user_id = await _register(session, telegram_id)
            payload = await _checkout(session, user_id)
            await _charge(
                session,
                telegram_id=telegram_id,
                payload=payload,
                charge_id=f"race-{telegram_id}",
                expires_at=expires,
            )

    counts = await asyncio.gather(
        process_due_subscriptions(session_factory, _settings(), now=expires),
        process_due_subscriptions(session_factory, _settings(), now=expires),
    )

    assert sum(counts) == len(telegram_ids)
    async with session_factory() as session:
        still_live = await session.scalar(
            select(func.count())
            .select_from(UserSubscription)
            .where(UserSubscription.status != SubscriptionStatus.EXPIRED.value)
        )
        assert still_live == 0
        # One grant per subscription: the sweep added none.
        assert await session.scalar(select(func.count()).select_from(SubscriptionGrant)) == len(
            telegram_ids
        )


@pytest.mark.asyncio
async def test_expiry_does_not_downgrade_a_user_already_on_another_tier(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    expires = datetime.now(UTC) + timedelta(days=30)
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 960_040)
        payload = await _checkout(session, user_id, slug="start")
        await _charge(
            session,
            telegram_id=960_040,
            payload=payload,
            charge_id="stale-1",
            expires_at=expires,
            stars=int(START["stars"]),
        )
        user = await UserRepository(session).get_by_id(user_id)
        assert user is not None
        user.plan = Plan.BUSINESS.value

    assert await process_due_subscriptions(session_factory, _settings(), now=expires) == 1
    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.BUSINESS.value


# --------------------------------------------------------------------- state and cancel


@pytest.mark.asyncio
async def test_cancelling_keeps_access_until_the_paid_period_ends(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_050)
    payload = await _checkout(session, user_id)
    expires = datetime.now(UTC) + timedelta(days=30)
    await _charge(
        session, telegram_id=960_050, payload=payload, charge_id="cx-1", expires_at=expires
    )

    result = await SubscriptionService(session, _settings()).request_cancel(user_id)

    assert result.root_charge_id == "cx-1"
    assert result.telegram_id == 960_050
    assert result.access_until == expires
    subscription = (await session.execute(select(UserSubscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.CANCELLING.value
    # Still paid for, therefore still entitled.
    assert await _plan_of(session, user_id) == Plan.PRO.value


@pytest.mark.asyncio
async def test_cancelling_a_never_charged_subscription_frees_the_slot(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_051)
    await _checkout(session, user_id, slug="start")
    service = SubscriptionService(session, _settings())

    await service.request_cancel(user_id)

    assert await service.get_state(user_id) is None
    # The slot is free, so a different plan can be started straight away.
    switched = await service.start_checkout(
        user_id, "pro", language=Language.RU, terms_accepted=True, accepted_terms_version="test-v1"
    )
    assert switched.plan_slug == "pro"


@pytest.mark.asyncio
async def test_telegram_states_are_recorded_without_revoking_access(
    session: AsyncSession,
) -> None:
    """`BotSubscriptionUpdated` reports a user-side cancel, a re-enable, or a failed
    renewal. None of those end a period that is already paid for."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_052)
    payload = await _checkout(session, user_id)
    service = SubscriptionService(session, _settings())
    await _charge(
        session,
        telegram_id=960_052,
        payload=payload,
        charge_id="st-1",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    assert await service.apply_telegram_state(invoice_payload=payload, state="canceled") is True
    state = await service.get_state(user_id)
    assert state is not None and state.status == SubscriptionStatus.CANCELLING
    assert state.cancel_at_period_end is True

    assert await service.apply_telegram_state(invoice_payload=payload, state="active") is True
    state = await service.get_state(user_id)
    assert state is not None and state.status == SubscriptionStatus.ACTIVE
    assert state.cancel_at_period_end is False

    assert await service.apply_telegram_state(invoice_payload=payload, state="failed") is True
    state = await service.get_state(user_id)
    assert state is not None and state.status == SubscriptionStatus.PAYMENT_FAILED
    assert state.renewal_failed is True
    # A failed renewal is a warning, not a revocation.
    assert await _plan_of(session, user_id) == Plan.PRO.value

    assert await service.apply_telegram_state(invoice_payload=payload, state="???") is False
    assert (
        await service.apply_telegram_state(invoice_payload="kelbet-sub:none", state="canceled")
        is False
    )


@pytest.mark.asyncio
async def test_a_charge_after_cancellation_means_the_user_re_enabled(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_053)
    payload = await _checkout(session, user_id)
    service = SubscriptionService(session, _settings())
    await _charge(
        session,
        telegram_id=960_053,
        payload=payload,
        charge_id="re-1",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await service.request_cancel(user_id)

    await _charge(
        session,
        telegram_id=960_053,
        payload=payload,
        charge_id="re-2",
        expires_at=datetime.now(UTC) + timedelta(days=60),
    )

    subscription = (await session.execute(select(UserSubscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    assert subscription.cancel_at_period_end is False
    assert subscription.cancelled_at is None


@pytest.mark.asyncio
async def test_pre_checkout_approves_a_valid_charge_and_rejects_the_rest(
    session: AsyncSession,
) -> None:
    """Without this the one-off path would answer `order_not_found` and Telegram would
    reject a perfectly good payment."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 960_060)
    payload = await _checkout(session, user_id)  # the pending row belongs to this user
    service = SubscriptionService(session, _settings())

    ok = await service.validate_pre_checkout(
        telegram_id=960_060,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(PRO["stars"]),
    )
    wrong_amount = await service.validate_pre_checkout(
        telegram_id=960_060,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(PRO["stars"]) - 1,
    )
    wrong_currency = await service.validate_pre_checkout(
        telegram_id=960_060,
        invoice_payload=payload,
        currency="USD",
        total_amount=int(PRO["stars"]),
    )
    other_buyer = await service.validate_pre_checkout(
        telegram_id=1,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(PRO["stars"]),
    )
    unknown = await service.validate_pre_checkout(
        telegram_id=960_060,
        invoice_payload="kelbet-sub:none",
        currency="XTR",
        total_amount=int(PRO["stars"]),
    )

    assert ok.ok is True
    assert wrong_amount.error_code == "amount_mismatch"
    assert wrong_currency.error_code == "currency_mismatch"
    assert other_buyer.error_code == "buyer_mismatch"
    assert unknown.error_code == "subscription_not_found"
