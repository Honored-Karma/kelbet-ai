"""Subscription lifecycle against a live Postgres.

The tests that matter here are the ones about money arriving more than once. Telegram
redelivers updates, so every path that grants credits is exercised twice — sequentially
and concurrently — and asserted to grant exactly one period's worth.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import CreditTransaction, Subscription, SubscriptionPeriod, Wallet
from kelbet.domain.enums import Language, Plan, SubscriptionStatus, TxReason
from kelbet.domain.exceptions import PaymentUnavailableError, PaymentValidationError
from kelbet.repositories.user import UserRepository
from kelbet.services.registration import RegistrationService
from kelbet.services.subscription import (
    SubscriptionService,
    is_subscription_payload,
    process_due_subscriptions,
)
from kelbet.subscriptions import seed_subscription_plans, subscription_plan_row

WELCOME_CREDITS = 60


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
        "welcome_credits": WELCOME_CREDITS,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _register(session: AsyncSession, telegram_id: int) -> UUID:
    user, _ = await RegistrationService(
        session, Settings(welcome_credits=WELCOME_CREDITS)
    ).register_with_language(
        telegram_id=telegram_id,
        username=f"sub_{telegram_id}",
        language=Language.RU,
    )
    return user.id


async def _balance(session: AsyncSession, user_id: UUID) -> int:
    wallet = (await session.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one()
    return wallet.balance


async def _plan_of(session: AsyncSession, user_id: UUID) -> str:
    user = await UserRepository(session).get_by_id(user_id)
    assert user is not None
    return user.plan


# --------------------------------------------------------------------------- routing


def test_payload_prefix_separates_subscriptions_from_one_off_packs() -> None:
    """The successful-payment handler routes on the payload alone, so the prefixes must
    not overlap. A pack payload matching the subscription prefix would send a one-off
    charge into the recurring path and vice versa."""
    assert is_subscription_payload("kelbet-sub:deadbeef")
    assert not is_subscription_payload("kelbet:deadbeef")
    assert not is_subscription_payload("")


# -------------------------------------------------------------------------- checkout


@pytest.mark.asyncio
async def test_checkout_is_gated_by_the_feature_flag(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_001)
    service = SubscriptionService(session, _settings(subscriptions_enabled=False))

    assert await service.list_plans(Language.RU) == []
    with pytest.raises(PaymentUnavailableError):
        await service.start_checkout(
            user_id=user_id,
            plan_slug="pro",
            idempotency_key="sub-flag-off",
            terms_accepted=True,
            language=Language.RU,
            accepted_terms_version="test-v1",
        )


@pytest.mark.asyncio
async def test_checkout_reserves_identity_without_moving_money(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_002)
    service = SubscriptionService(session, _settings())

    checkout = await service.start_checkout(
        user_id=user_id,
        plan_slug="pro",
        idempotency_key="sub-checkout-1",
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )

    pro = subscription_plan_row("pro")
    assert checkout.stars == pro["stars"]
    assert checkout.monthly_credits == pro["monthly_credits"]
    assert checkout.currency == "XTR"
    # Telegram accepts exactly one period length today; anything else is rejected.
    assert checkout.subscription_period_seconds == 2_592_000
    assert is_subscription_payload(checkout.invoice_payload)

    # No period, no credits, still on free until a charge actually lands.
    assert await _balance(session, user_id) == WELCOME_CREDITS
    assert await _plan_of(session, user_id) == Plan.FREE.value
    assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 0


@pytest.mark.asyncio
async def test_repeated_checkout_returns_the_same_pending_subscription(
    session: AsyncSession,
) -> None:
    """A user tapping the subscribe button twice must not end up billed twice."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_003)
    service = SubscriptionService(session, _settings())

    first = await service.start_checkout(
        user_id=user_id,
        plan_slug="start",
        idempotency_key="sub-dup-1",
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )
    second = await service.start_checkout(
        user_id=user_id,
        plan_slug="start",
        idempotency_key="sub-dup-2",
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )

    assert first.subscription_id == second.subscription_id
    assert first.invoice_payload == second.invoice_payload
    assert await session.scalar(select(func.count()).select_from(Subscription)) == 1


@pytest.mark.asyncio
async def test_switching_tier_requires_cancelling_the_running_one(
    session: AsyncSession,
) -> None:
    """Two live subscriptions would bill the user twice for overlapping periods."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_004)
    service = SubscriptionService(session, _settings())
    await service.start_checkout(
        user_id=user_id,
        plan_slug="start",
        idempotency_key="sub-switch-1",
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )

    with pytest.raises(PaymentValidationError, match="Cancel the current subscription"):
        await service.start_checkout(
            user_id=user_id,
            plan_slug="pro",
            idempotency_key="sub-switch-2",
            terms_accepted=True,
            language=Language.RU,
            accepted_terms_version="test-v1",
        )


@pytest.mark.asyncio
async def test_terms_must_be_accepted_and_current(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_005)
    service = SubscriptionService(session, _settings())

    with pytest.raises(PaymentValidationError, match="Terms must be accepted"):
        await service.start_checkout(
            user_id=user_id,
            plan_slug="pro",
            idempotency_key="sub-terms-1",
            terms_accepted=False,
            language=Language.RU,
            accepted_terms_version="test-v1",
        )
    with pytest.raises(PaymentValidationError, match="no longer current"):
        await service.start_checkout(
            user_id=user_id,
            plan_slug="pro",
            idempotency_key="sub-terms-2",
            terms_accepted=True,
            language=Language.RU,
            accepted_terms_version="stale-version",
        )


# ----------------------------------------------------------------------------- money


async def _checkout(
    session: AsyncSession,
    user_id: UUID,
    *,
    plan_slug: str = "pro",
    key: str = "sub-pay",
) -> str:
    checkout = await SubscriptionService(session, _settings()).start_checkout(
        user_id=user_id,
        plan_slug=plan_slug,
        idempotency_key=key,
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )
    return checkout.invoice_payload


@pytest.mark.asyncio
async def test_first_charge_activates_the_plan_and_grants_one_period(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_010)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    expires = datetime.now(UTC) + timedelta(days=30)

    result = await SubscriptionService(session, _settings()).apply_successful_payment(
        telegram_id=940_010,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-charge-1",
        provider_payment_charge_id=None,
        subscription_expiration_date=expires,
        is_first_recurring=True,
    )

    assert result.applied is True
    assert result.credits == pro["monthly_credits"]
    assert result.plan == Plan.PRO
    assert result.balance == WELCOME_CREDITS + int(pro["monthly_credits"])
    assert result.period_end == expires
    assert await _plan_of(session, user_id) == Plan.PRO.value

    subscription = (await session.execute(select(Subscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    # The charge id has to be kept: editUserStarSubscription addresses the subscription
    # by it, so losing it would make cancellation impossible.
    assert subscription.root_charge_id == "sub-charge-1"
    assert subscription.renewal_count == 0
    # The expiry date is Telegram's, never computed locally.
    assert subscription.current_period_end == expires


@pytest.mark.asyncio
async def test_redelivered_charge_grants_credits_exactly_once(session: AsyncSession) -> None:
    """Telegram retries updates. The same charge id must never pay out twice."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_011)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    expires = datetime.now(UTC) + timedelta(days=30)

    async def deliver() -> object:
        return await service.apply_successful_payment(
            telegram_id=940_011,
            invoice_payload=payload,
            currency="XTR",
            total_amount=int(pro["stars"]),
            telegram_payment_charge_id="sub-charge-replay",
            provider_payment_charge_id=None,
            subscription_expiration_date=expires,
            is_first_recurring=True,
        )

    first = await deliver()
    second = await deliver()

    assert first.applied is True  # type: ignore[attr-defined]
    assert second.applied is False  # type: ignore[attr-defined]
    # A replay still reports the period's credits, so the user gets a correct message.
    assert second.credits == pro["monthly_credits"]  # type: ignore[attr-defined]
    assert await _balance(session, user_id) == WELCOME_CREDITS + int(pro["monthly_credits"])
    assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 1
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
    """Two workers handed the same charge simultaneously. The row lock and the unique
    charge id must serialise them into a single grant."""
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 940_012)
        payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    expires = datetime.now(UTC) + timedelta(days=30)

    async def deliver() -> bool:
        async with session_factory() as session, session.begin():
            result = await SubscriptionService(session, _settings()).apply_successful_payment(
                telegram_id=940_012,
                invoice_payload=payload,
                currency="XTR",
                total_amount=int(pro["stars"]),
                telegram_payment_charge_id="sub-charge-concurrent",
                provider_payment_charge_id=None,
                subscription_expiration_date=expires,
                is_first_recurring=True,
            )
            return result.applied

    outcomes = await asyncio.gather(deliver(), deliver())

    assert sorted(outcomes) == [False, True]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 1
        assert await _balance(session, user_id) == WELCOME_CREDITS + int(pro["monthly_credits"])


@pytest.mark.asyncio
async def test_renewal_grants_another_period_and_extends_the_deadline(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_013)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    first_end = datetime.now(UTC) + timedelta(days=30)
    second_end = first_end + timedelta(days=30)

    await service.apply_successful_payment(
        telegram_id=940_013,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-renew-1",
        provider_payment_charge_id=None,
        subscription_expiration_date=first_end,
        is_first_recurring=True,
    )
    # A renewal reuses the original payload with a new charge id. This is exactly the case
    # the one-off `payment_orders` path would have rejected as a duplicate charge.
    renewal = await service.apply_successful_payment(
        telegram_id=940_013,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-renew-2",
        provider_payment_charge_id=None,
        subscription_expiration_date=second_end,
    )

    assert renewal.applied is True
    assert await _balance(session, user_id) == WELCOME_CREDITS + 2 * int(pro["monthly_credits"])
    subscription = (await session.execute(select(Subscription))).scalar_one()
    assert subscription.renewal_count == 1
    assert subscription.current_period_end == second_end
    assert subscription.root_charge_id == "sub-renew-1"
    assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 2


@pytest.mark.asyncio
async def test_wrong_amount_and_wrong_buyer_never_grant_credits(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_014)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    expires = datetime.now(UTC) + timedelta(days=30)

    underpaid = await service.apply_successful_payment(
        telegram_id=940_014,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]) - 1,
        telegram_payment_charge_id="sub-bad-amount",
        provider_payment_charge_id=None,
        subscription_expiration_date=expires,
    )
    other_buyer = await service.apply_successful_payment(
        telegram_id=999_999,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-bad-buyer",
        provider_payment_charge_id=None,
        subscription_expiration_date=expires,
    )
    unknown = await service.apply_successful_payment(
        telegram_id=940_014,
        invoice_payload="kelbet-sub:does-not-exist",
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-bad-payload",
        provider_payment_charge_id=None,
        subscription_expiration_date=expires,
    )

    assert underpaid.error_code == "amount_mismatch"
    assert other_buyer.error_code == "buyer_mismatch"
    assert unknown.error_code == "subscription_not_found"
    assert await _balance(session, user_id) == WELCOME_CREDITS
    assert await _plan_of(session, user_id) == Plan.FREE.value
    assert await session.scalar(select(func.count()).select_from(SubscriptionPeriod)) == 0


@pytest.mark.asyncio
async def test_repricing_a_plan_does_not_change_an_existing_subscription(
    session: AsyncSession,
) -> None:
    """The snapshot is the agreed price. A repriced plan must not make a subscriber's
    charge look wrong, nor silently change what they receive."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_015)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    original_stars = int(pro["stars"])
    original_credits = int(pro["monthly_credits"])

    subscription = (await session.execute(select(Subscription))).scalar_one()
    plan = await SubscriptionService(session, _settings())._subscriptions.get_plan_by_id(
        subscription.plan_id
    )
    assert plan is not None
    plan.stars = original_stars + 500
    plan.monthly_credits = original_credits + 500
    await session.flush()

    result = await SubscriptionService(session, _settings()).apply_successful_payment(
        telegram_id=940_015,
        invoice_payload=payload,
        currency="XTR",
        total_amount=original_stars,
        telegram_payment_charge_id="sub-reprice",
        provider_payment_charge_id=None,
        subscription_expiration_date=datetime.now(UTC) + timedelta(days=30),
        is_first_recurring=True,
    )

    assert result.applied is True
    assert result.credits == original_credits


# --------------------------------------------------------------------- state changes


@pytest.mark.asyncio
async def test_cancelling_keeps_access_until_the_paid_period_ends(
    session: AsyncSession,
) -> None:
    """Telegram guarantees the subscription stays active to the end of the paid period, so
    cancelling must never revoke the plan early."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_020)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    expires = datetime.now(UTC) + timedelta(days=30)
    await service.apply_successful_payment(
        telegram_id=940_020,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-cancel-1",
        provider_payment_charge_id=None,
        subscription_expiration_date=expires,
        is_first_recurring=True,
    )

    cancel = await service.request_cancel(user_id=user_id)

    assert cancel.root_charge_id == "sub-cancel-1"
    assert cancel.telegram_id == 940_020
    assert cancel.current_period_end == expires
    subscription = (await session.execute(select(Subscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.CANCELLED.value
    assert subscription.cancel_at_period_end is True
    # Still paid for, therefore still on the plan.
    assert await _plan_of(session, user_id) == Plan.PRO.value


@pytest.mark.asyncio
async def test_cancelling_a_never_charged_subscription_frees_the_slot(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_021)
    service = SubscriptionService(session, _settings())
    await _checkout(session, user_id, plan_slug="start", key="sub-pending-cancel")

    await service.request_cancel(user_id=user_id)

    # Retired immediately, so the user can subscribe to a different tier straight away.
    assert await service.get_state(user_id, Language.RU) is None
    switched = await service.start_checkout(
        user_id=user_id,
        plan_slug="pro",
        idempotency_key="sub-after-pending-cancel",
        terms_accepted=True,
        language=Language.RU,
        accepted_terms_version="test-v1",
    )
    assert switched.plan_slug == "pro"


@pytest.mark.asyncio
async def test_cancelling_without_a_subscription_is_rejected(session: AsyncSession) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_022)
    with pytest.raises(PaymentValidationError, match="No active subscription"):
        await SubscriptionService(session, _settings()).request_cancel(user_id=user_id)


@pytest.mark.asyncio
async def test_telegram_reported_states_are_recorded_without_revoking_access(
    session: AsyncSession,
) -> None:
    """`BotSubscriptionUpdated` tells us the user cancelled, re-enabled, or that a renewal
    failed. None of those end the period that is already paid for."""
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_023)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    await service.apply_successful_payment(
        telegram_id=940_023,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-state-1",
        provider_payment_charge_id=None,
        subscription_expiration_date=datetime.now(UTC) + timedelta(days=30),
        is_first_recurring=True,
    )

    assert await service.apply_telegram_state(invoice_payload=payload, state="canceled") is True
    state = await service.get_state(user_id, Language.RU)
    assert state is not None and state.status == SubscriptionStatus.CANCELLED.value
    assert state.cancel_at_period_end is True

    assert await service.apply_telegram_state(invoice_payload=payload, state="active") is True
    state = await service.get_state(user_id, Language.RU)
    assert state is not None and state.status == SubscriptionStatus.ACTIVE.value
    assert state.cancel_at_period_end is False

    assert await service.apply_telegram_state(invoice_payload=payload, state="failed") is True
    state = await service.get_state(user_id, Language.RU)
    assert state is not None and state.status == SubscriptionStatus.PAYMENT_FAILED.value
    assert state.renewal_failed is True
    # A failed renewal is a warning, not a revocation: the paid period still runs.
    assert await _plan_of(session, user_id) == Plan.PRO.value

    assert await service.apply_telegram_state(invoice_payload=payload, state="nonsense") is False
    assert (
        await service.apply_telegram_state(invoice_payload="kelbet-sub:nope", state="canceled")
        is False
    )


@pytest.mark.asyncio
async def test_a_charge_after_cancellation_means_the_user_re_enabled(
    session: AsyncSession,
) -> None:
    await seed_subscription_plans(session)
    user_id = await _register(session, 940_024)
    payload = await _checkout(session, user_id)
    pro = subscription_plan_row("pro")
    service = SubscriptionService(session, _settings())
    await service.apply_successful_payment(
        telegram_id=940_024,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-reenable-1",
        provider_payment_charge_id=None,
        subscription_expiration_date=datetime.now(UTC) + timedelta(days=30),
        is_first_recurring=True,
    )
    await service.request_cancel(user_id=user_id)

    await service.apply_successful_payment(
        telegram_id=940_024,
        invoice_payload=payload,
        currency="XTR",
        total_amount=int(pro["stars"]),
        telegram_payment_charge_id="sub-reenable-2",
        provider_payment_charge_id=None,
        subscription_expiration_date=datetime.now(UTC) + timedelta(days=60),
    )

    subscription = (await session.execute(select(Subscription))).scalar_one()
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    assert subscription.cancel_at_period_end is False
    assert subscription.cancelled_at is None


# ---------------------------------------------------------------------------- expiry


@pytest.mark.asyncio
async def test_expiry_downgrades_only_after_the_paid_period_ends(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 940_030)
        payload = await _checkout(session, user_id)
        pro = subscription_plan_row("pro")
        expires = datetime.now(UTC) + timedelta(days=30)
        await SubscriptionService(session, _settings()).apply_successful_payment(
            telegram_id=940_030,
            invoice_payload=payload,
            currency="XTR",
            total_amount=int(pro["stars"]),
            telegram_payment_charge_id="sub-expire-1",
            provider_payment_charge_id=None,
            subscription_expiration_date=expires,
            is_first_recurring=True,
        )

    settings = _settings()
    # One second before the deadline nothing may happen.
    assert (
        await process_due_subscriptions(
            session_factory, settings, now=expires - timedelta(seconds=1)
        )
        == 0
    )
    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.PRO.value

    assert await process_due_subscriptions(session_factory, settings, now=expires) == 1
    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.FREE.value
        subscription = (await session.execute(select(Subscription))).scalar_one()
        assert subscription.status == SubscriptionStatus.EXPIRED.value
        # Credits already granted are the user's; expiry only removes the tier.
        assert await _balance(session, user_id) == WELCOME_CREDITS + int(pro["monthly_credits"])

    # Idempotent: a second sweep finds nothing left to do.
    assert await process_due_subscriptions(session_factory, settings, now=expires) == 0


@pytest.mark.asyncio
async def test_two_concurrent_workers_expire_each_subscription_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`skip_locked` is what makes this safe: the second worker must skip rows the first
    holds rather than block on them or process them twice."""
    expires = datetime.now(UTC) + timedelta(days=30)
    pro = subscription_plan_row("pro")
    telegram_ids = [940_040 + index for index in range(6)]
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        for telegram_id in telegram_ids:
            user_id = await _register(session, telegram_id)
            payload = await _checkout(session, user_id, key=f"sub-race-{telegram_id}")
            await SubscriptionService(session, _settings()).apply_successful_payment(
                telegram_id=telegram_id,
                invoice_payload=payload,
                currency="XTR",
                total_amount=int(pro["stars"]),
                telegram_payment_charge_id=f"sub-race-charge-{telegram_id}",
                provider_payment_charge_id=None,
                subscription_expiration_date=expires,
                is_first_recurring=True,
            )

    settings = _settings()
    counts = await asyncio.gather(
        process_due_subscriptions(session_factory, settings, now=expires),
        process_due_subscriptions(session_factory, settings, now=expires),
    )

    assert sum(counts) == len(telegram_ids)
    async with session_factory() as session:
        expired = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SubscriptionStatus.EXPIRED.value)
        )
        assert expired == len(telegram_ids)
        remaining_paid = await session.scalar(
            select(func.count()).select_from(Subscription).where(Subscription.status != "expired")
        )
        assert remaining_paid == 0


@pytest.mark.asyncio
async def test_expiry_does_not_downgrade_a_user_who_already_moved_to_another_tier(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A stale expiry arriving after an upgrade must not knock the user back to free."""
    expires = datetime.now(UTC) + timedelta(days=30)
    start = subscription_plan_row("start")
    async with session_factory() as session, session.begin():
        await seed_subscription_plans(session)
        user_id = await _register(session, 940_050)
        payload = await _checkout(session, user_id, plan_slug="start", key="sub-stale-1")
        service = SubscriptionService(session, _settings())
        await service.apply_successful_payment(
            telegram_id=940_050,
            invoice_payload=payload,
            currency="XTR",
            total_amount=int(start["stars"]),
            telegram_payment_charge_id="sub-stale-charge",
            provider_payment_charge_id=None,
            subscription_expiration_date=expires,
            is_first_recurring=True,
        )
        # The user has since been moved to a richer tier by another path.
        user = await UserRepository(session).get_by_id(user_id)
        assert user is not None
        user.plan = Plan.BUSINESS.value

    assert await process_due_subscriptions(session_factory, _settings(), now=expires) == 1
    async with session_factory() as session:
        assert await _plan_of(session, user_id) == Plan.BUSINESS.value
