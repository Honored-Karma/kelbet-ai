from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apps.bot.handlers.start import referral_code_from_start
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings
from kelbet.db.models import (
    FeatureFlag,
    PaymentOrder,
    PaymentProduct,
    PaymentReceipt,
    ReferralAttribution,
    ReferralReward,
    Wallet,
)
from kelbet.domain.enums import Language, PaymentReceiptStatus, PaymentStatus, TxReason
from kelbet.payments.gateway import StarTransactionRecord
from kelbet.services.payment_reconciliation import reconcile_star_transactions
from kelbet.services.referral import ReferralService, process_due_referral_rewards
from kelbet.services.registration import RegistrationService
from kelbet.services.wallet import WalletService


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "welcome_credits": 5,
        "referral_bot_username": "kelbet_test_bot",
        "referral_inviter_bonus_credits": 5,
        "referral_invitee_bonus_credits": 2,
        "referral_minimum_purchase_stars": 50,
        "referral_waiting_period_hours": 0,
        "referral_daily_reward_limit": 20,
        "referral_suspicious_daily_attribution_threshold": 50,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _enable_referrals(session: AsyncSession) -> None:
    await seed_catalog(session)
    flag = await session.get(FeatureFlag, "referrals")
    assert flag is not None
    flag.enabled = True
    flag.payload = {}


async def _register(
    session: AsyncSession,
    settings: Settings,
    telegram_id: int,
    *,
    code: str | None = None,
) -> UUID:
    user, _credit = await RegistrationService(session, settings).register_with_language(
        telegram_id=telegram_id,
        username=f"ref_{telegram_id}",
        language=Language.RU,
        referral_code=code,
    )
    return user.id


async def _create_paid_order(
    session: AsyncSession,
    *,
    user_id: UUID,
    telegram_id: int,
    stars: int,
    charge_id: str,
    now: datetime,
) -> PaymentOrder:
    product = PaymentProduct(
        slug=f"ref-test-{uuid4().hex[:10]}",
        credits=100,
        stars=stars,
        enabled=True,
        display_order=1,
        localization={},
    )
    session.add(product)
    await session.flush()
    order = PaymentOrder(
        user_id=user_id,
        product_id=product.id,
        status=PaymentStatus.PAID.value,
        idempotency_key=f"order:{charge_id}",
        invoice_payload=f"kelbet:{uuid4().hex}",
        currency="XTR",
        total_amount=stars,
        credits=100,
        product_snapshot={"slug": product.slug},
        terms_version="test-v1",
        terms_accepted_at=now,
        expires_at=now + timedelta(minutes=30),
        paid_at=now,
    )
    session.add(order)
    await session.flush()
    wallet = (await session.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one()
    purchase = await WalletService(session).credit(
        wallet.id,
        100,
        TxReason.PAYMENT_PURCHASE,
        f"stars:{charge_id}",
        meta={"telegram_payment_charge_id": charge_id, "payment_order_id": str(order.id)},
    )
    order.ledger_transaction_id = purchase.transaction_id
    session.add(
        PaymentReceipt(
            order_id=order.id,
            telegram_user_id=telegram_id,
            telegram_payment_charge_id=charge_id,
            provider_payment_charge_id=None,
            invoice_payload=order.invoice_payload,
            currency="XTR",
            total_amount=stars,
            status=PaymentReceiptStatus.PROCESSED.value,
            error_code=None,
            created_at=now,
            processed_at=now,
        )
    )
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_new_user_attribution_is_first_touch_and_immutable(
    session: AsyncSession,
) -> None:
    settings = _settings()
    await _enable_referrals(session)
    inviter_id = await _register(session, settings, 970_001)
    second_inviter_id = await _register(session, settings, 970_002)
    first = await ReferralService(session, settings).get_summary(inviter_id)
    second = await ReferralService(session, settings).get_summary(second_inviter_id)
    assert first.enabled and first.code and first.link
    assert second.code
    assert referral_code_from_start(f"ref_{first.code}") == first.code
    assert referral_code_from_start("ref_unsafe value") is None

    invited_id = await _register(session, settings, 970_003, code=first.code)
    repeated_id = await _register(session, settings, 970_003, code=second.code)
    assert repeated_id == invited_id
    attribution = (
        await session.execute(
            select(ReferralAttribution).where(ReferralAttribution.invited_user_id == invited_id)
        )
    ).scalar_one()
    assert attribution.inviter_user_id == inviter_id
    reward = (
        await session.execute(
            select(ReferralReward).where(ReferralReward.attribution_id == attribution.id)
        )
    ).scalar_one()
    assert reward.status == "pending"


@pytest.mark.asyncio
async def test_existing_unknown_and_self_referrals_are_rejected(session: AsyncSession) -> None:
    settings = _settings()
    await _enable_referrals(session)
    inviter_id = await _register(session, settings, 970_010)
    summary = await ReferralService(session, settings).get_summary(inviter_id)
    assert summary.code

    assert (
        await ReferralService(session, settings).attribute_new_user(
            invited_user_id=inviter_id,
            code=summary.code,
            created_in_registration=True,
        )
        is None
    )
    existing_id = await _register(session, settings, 970_011)
    await _register(session, settings, 970_011, code=summary.code)
    assert (
        await ReferralService(session, settings).attribute_new_user(
            invited_user_id=existing_id,
            code=summary.code,
        )
        is None
    )
    assert (
        await ReferralService(session, settings).attribute_new_user(
            invited_user_id=existing_id,
            code="UNKNOWN01",
            created_in_registration=True,
        )
        is None
    )
    count = await session.scalar(select(func.count()).select_from(ReferralAttribution))
    assert count == 0


@pytest.mark.asyncio
async def test_disabled_referrals_do_not_expose_links_or_create_attribution(
    session: AsyncSession,
) -> None:
    settings = _settings()
    await _enable_referrals(session)
    inviter_id = await _register(session, settings, 970_012)
    enabled = await ReferralService(session, settings).get_summary(inviter_id)
    assert enabled.code
    flag = await session.get(FeatureFlag, "referrals")
    assert flag is not None
    flag.enabled = False
    await session.flush()

    disabled = await ReferralService(session, settings).get_summary(inviter_id)
    assert disabled.enabled is False
    assert disabled.code is None
    assert disabled.link is None
    await _register(session, settings, 970_013, code=enabled.code)
    count = await session.scalar(select(func.count()).select_from(ReferralAttribution))
    assert count == 0


@pytest.mark.asyncio
async def test_reconciled_first_purchase_credits_once_and_chargeback_never_claws_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        await _enable_referrals(session)
        inviter_id = await _register(session, settings, 970_020)
        summary = await ReferralService(session, settings).get_summary(inviter_id)
        assert summary.code
        invited_id = await _register(session, settings, 970_021, code=summary.code)
        order = await _create_paid_order(
            session,
            user_id=invited_id,
            telegram_id=970_021,
            stars=100,
            charge_id="ref-charge-1",
            now=now,
        )
        order_id = order.id
        await reconcile_star_transactions(
            session,
            [
                StarTransactionRecord(
                    transaction_id="ref-charge-1",
                    amount=100,
                    occurred_at=now,
                    direction="incoming",
                    partner_type="user",
                    transaction_type=None,
                )
            ],
            settings=settings,
            now=now,
        )

    assert await process_due_referral_rewards(session_factory, settings, now=now) == 1
    assert await process_due_referral_rewards(session_factory, settings, now=now) == 0
    async with session_factory() as session, session.begin():
        reward = (await session.execute(select(ReferralReward))).scalar_one()
        assert reward.status == "credited"
        inviter_wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == inviter_id))
        ).scalar_one()
        invitee_wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == invited_id))
        ).scalar_one()
        assert inviter_wallet.balance == 10
        assert invitee_wallet.balance == 107
        await reconcile_star_transactions(
            session,
            [
                StarTransactionRecord(
                    transaction_id="ref-charge-1",
                    amount=100,
                    occurred_at=now,
                    direction="outgoing",
                    partner_type="user",
                    transaction_type="chargeback",
                )
            ],
            settings=settings,
            now=now + timedelta(minutes=1),
        )
        reward = (await session.execute(select(ReferralReward))).scalar_one()
        assert reward.status == "needs_review"
        assert reward.review_reason == "payment_reversed_after_credit"
        assert reward.payment_order_id == order_id
        assert inviter_wallet.balance == 10
        assert invitee_wallet.balance == 107


@pytest.mark.asyncio
async def test_refund_before_waiting_period_cancels_reward_without_wallet_debit(
    session: AsyncSession,
) -> None:
    settings = _settings(referral_waiting_period_hours=72)
    now = datetime.now(UTC)
    await _enable_referrals(session)
    inviter_id = await _register(session, settings, 970_030)
    summary = await ReferralService(session, settings).get_summary(inviter_id)
    assert summary.code
    invited_id = await _register(session, settings, 970_031, code=summary.code)
    await _create_paid_order(
        session,
        user_id=invited_id,
        telegram_id=970_031,
        stars=100,
        charge_id="ref-charge-2",
        now=now,
    )
    incoming = StarTransactionRecord(
        transaction_id="ref-charge-2",
        amount=100,
        occurred_at=now,
        direction="incoming",
        partner_type="user",
        transaction_type=None,
    )
    await reconcile_star_transactions(session, [incoming], settings=settings, now=now)
    reward = (await session.execute(select(ReferralReward))).scalar_one()
    assert reward.status == "eligible"
    await reconcile_star_transactions(
        session,
        [
            StarTransactionRecord(
                transaction_id="ref-charge-2",
                amount=100,
                occurred_at=now,
                direction="outgoing",
                partner_type="user",
                transaction_type="refund",
            )
        ],
        settings=settings,
        now=now + timedelta(hours=1),
    )
    assert reward.status == "cancelled"
    assert reward.review_reason == "payment_reversed_before_credit"
    inviter_wallet = (
        await session.execute(select(Wallet).where(Wallet.user_id == inviter_id))
    ).scalar_one()
    assert inviter_wallet.balance == 5


@pytest.mark.asyncio
async def test_first_purchase_below_minimum_cancels_reward(session: AsyncSession) -> None:
    settings = _settings(referral_minimum_purchase_stars=50)
    now = datetime.now(UTC)
    await _enable_referrals(session)
    inviter_id = await _register(session, settings, 970_032)
    summary = await ReferralService(session, settings).get_summary(inviter_id)
    assert summary.code
    invited_id = await _register(session, settings, 970_033, code=summary.code)
    await _create_paid_order(
        session,
        user_id=invited_id,
        telegram_id=970_033,
        stars=49,
        charge_id="ref-charge-below-minimum",
        now=now,
    )
    await reconcile_star_transactions(
        session,
        [
            StarTransactionRecord(
                transaction_id="ref-charge-below-minimum",
                amount=49,
                occurred_at=now,
                direction="incoming",
                partner_type="user",
                transaction_type=None,
            )
        ],
        settings=settings,
        now=now,
    )
    reward = (await session.execute(select(ReferralReward))).scalar_one()
    assert reward.status == "cancelled"
    assert reward.review_reason == "first_purchase_below_minimum"
    inviter_wallet = (
        await session.execute(select(Wallet).where(Wallet.user_id == inviter_id))
    ).scalar_one()
    assert inviter_wallet.balance == 5


@pytest.mark.asyncio
async def test_daily_reward_limit_postpones_excess_reward(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(referral_daily_reward_limit=1)
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    async with session_factory() as session, session.begin():
        await _enable_referrals(session)
        inviter_id = await _register(session, settings, 970_034)
        summary = await ReferralService(session, settings).get_summary(inviter_id)
        assert summary.code
        transactions: list[StarTransactionRecord] = []
        for telegram_id, charge_id in (
            (970_035, "ref-daily-charge-1"),
            (970_036, "ref-daily-charge-2"),
        ):
            invited_id = await _register(session, settings, telegram_id, code=summary.code)
            await _create_paid_order(
                session,
                user_id=invited_id,
                telegram_id=telegram_id,
                stars=100,
                charge_id=charge_id,
                now=now,
            )
            transactions.append(
                StarTransactionRecord(
                    transaction_id=charge_id,
                    amount=100,
                    occurred_at=now,
                    direction="incoming",
                    partner_type="user",
                    transaction_type=None,
                )
            )
        await reconcile_star_transactions(session, transactions, settings=settings, now=now)

    assert await process_due_referral_rewards(session_factory, settings, now=now) == 2
    async with session_factory() as session:
        rewards = list(
            (await session.execute(select(ReferralReward).order_by(ReferralReward.created_at)))
            .scalars()
            .all()
        )
        assert [reward.status for reward in rewards].count("credited") == 1
        assert [reward.status for reward in rewards].count("eligible") == 1
        postponed = next(reward for reward in rewards if reward.status == "eligible")
        assert postponed.eligible_at == now.replace(hour=0) + timedelta(days=1)

    next_day = now + timedelta(days=1, minutes=1)
    assert await process_due_referral_rewards(session_factory, settings, now=next_day) == 1
    async with session_factory() as session:
        statuses = list((await session.execute(select(ReferralReward.status))).scalars().all())
        inviter_wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == inviter_id))
        ).scalar_one()
    assert statuses == ["credited", "credited"]
    assert inviter_wallet.balance == 15


@pytest.mark.asyncio
async def test_concurrent_registration_creates_one_attribution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings()
    async with session_factory() as session, session.begin():
        await _enable_referrals(session)
        inviter_id = await _register(session, settings, 970_040)
        summary = await ReferralService(session, settings).get_summary(inviter_id)
        assert summary.code
        code = summary.code

    async def register_once() -> UUID:
        async with session_factory() as session, session.begin():
            return await _register(session, settings, 970_041, code=code)

    first_id, second_id = await asyncio.gather(register_once(), register_once())
    assert first_id == second_id
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ReferralAttribution))
        assert count == 1
