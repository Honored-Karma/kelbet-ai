from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings
from kelbet.db.models import CreditTransaction, PaymentOrder, PaymentReceipt, Wallet
from kelbet.domain.enums import Language, PaymentReceiptStatus, PaymentStatus, TxReason
from kelbet.payments import seed_payment_products
from kelbet.services.payment import PaymentService
from kelbet.services.registration import RegistrationService


def _settings() -> Settings:
    return Settings(
        payments_enabled=True,
        payment_terms_url="https://kelbet.ai/terms",
        payment_terms_version="test-v1",
        payment_order_ttl_minutes=30,
        support_username="kelbet_support",
    )


@pytest.mark.asyncio
async def test_stars_payment_is_validated_and_credited_exactly_once(
    session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    settings = _settings()
    await seed_payment_products(session)
    user, _welcome = await RegistrationService(
        session, Settings(welcome_credits=5)
    ).register_with_language(
        telegram_id=920_001,
        username="stars_user",
        language=Language.KK,
    )
    service = PaymentService(session, settings)

    products = await service.list_products(Language.KK)
    assert [product.slug for product in products] == ["starter", "creator", "studio"]
    assert products[0].name == "Бастау"

    order = await service.create_order(
        user_id=user.id,
        product_slug="starter",
        idempotency_key="payment-order-1",
        terms_accepted=True,
        language=Language.KK,
        now=now,
    )
    assert order.currency == "XTR"
    assert order.total_amount == 100
    assert order.credits == 100

    wrong = await service.validate_pre_checkout(
        telegram_id=user.telegram_id,
        query_id="pre-wrong",
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=99,
        now=now,
    )
    assert wrong.ok is False
    assert wrong.error_code == "amount_mismatch"

    approved = await service.validate_pre_checkout(
        telegram_id=user.telegram_id,
        query_id="pre-ok",
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=100,
        now=now,
    )
    assert approved.ok is True

    first = await service.complete_payment(
        telegram_id=user.telegram_id,
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=100,
        telegram_payment_charge_id="tg-charge-001",
        provider_payment_charge_id="",
        now=now + timedelta(seconds=2),
    )
    assert first.processed is True
    assert first.applied is True
    assert first.credits == 100
    assert first.balance == 105

    duplicate = await service.complete_payment(
        telegram_id=user.telegram_id,
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=100,
        telegram_payment_charge_id="tg-charge-001",
        provider_payment_charge_id="",
        now=now + timedelta(seconds=3),
    )
    assert duplicate.processed is True
    assert duplicate.applied is False
    assert duplicate.balance == 105

    wallet = (
        await session.execute(select(Wallet).where(Wallet.user_id == user.id))
    ).scalar_one()
    stored_order = (
        await session.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
    ).scalar_one()
    receipt = (
        await session.execute(
            select(PaymentReceipt).where(
                PaymentReceipt.telegram_payment_charge_id == "tg-charge-001"
            )
        )
    ).scalar_one()
    purchase_count = await session.scalar(
        select(func.count())
        .select_from(CreditTransaction)
        .where(CreditTransaction.reason == TxReason.PAYMENT_PURCHASE.value)
    )
    assert wallet.balance == 105
    assert stored_order.status == PaymentStatus.PAID.value
    assert stored_order.ledger_transaction_id is not None
    assert receipt.status == PaymentReceiptStatus.PROCESSED.value
    assert purchase_count == 1


@pytest.mark.asyncio
async def test_invalid_successful_payment_is_preserved_without_credit(
    session: AsyncSession,
) -> None:
    settings = _settings()
    await seed_payment_products(session)
    user, _welcome = await RegistrationService(
        session, Settings(welcome_credits=5)
    ).register_with_language(
        telegram_id=920_002,
        username="stars_review",
        language=Language.RU,
    )
    service = PaymentService(session, settings)
    order = await service.create_order(
        user_id=user.id,
        product_slug="creator",
        idempotency_key="payment-order-review",
        terms_accepted=True,
        language=Language.RU,
    )

    result = await service.complete_payment(
        telegram_id=user.telegram_id,
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=1,
        telegram_payment_charge_id="tg-charge-review",
        provider_payment_charge_id=None,
    )
    assert result.processed is False
    assert result.error_code == "amount_mismatch"

    receipt = (
        await session.execute(
            select(PaymentReceipt).where(
                PaymentReceipt.telegram_payment_charge_id == "tg-charge-review"
            )
        )
    ).scalar_one()
    wallet = (
        await session.execute(select(Wallet).where(Wallet.user_id == user.id))
    ).scalar_one()
    assert receipt.status == PaymentReceiptStatus.REJECTED.value
    assert receipt.error_code == "amount_mismatch"
    assert wallet.balance == 5
