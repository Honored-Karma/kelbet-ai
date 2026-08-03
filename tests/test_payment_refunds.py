from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import (
    CreditTransaction,
    PaymentOrder,
    PaymentReconciliationIssue,
    PaymentRefund,
    Wallet,
)
from kelbet.domain.enums import Language, PaymentRefundStatus, PaymentStatus, TxReason
from kelbet.domain.exceptions import PaymentRefundConflictError
from kelbet.payments import seed_payment_products
from kelbet.payments.gateway import (
    FakeStarsGateway,
    StarsGatewayError,
    StarTransactionRecord,
)
from kelbet.payments.seeds import payment_product_rows
from kelbet.services.payment import PaymentService, payment_production_gate_failures
from kelbet.services.payment_reconciliation import reconcile_star_transactions
from kelbet.services.payment_refund import PaymentRefundService, process_due_refund
from kelbet.services.registration import RegistrationService
from kelbet.services.wallet import WalletService


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "payments_enabled": True,
        "payment_terms_url": "https://kelbet.ai/terms",
        "payment_refund_policy_url": "https://kelbet.ai/refunds",
        "payment_terms_version": "test-v1",
        "payment_seller_identity": "KELBET TEST SELLER",
        "payment_finance_review_confirmed": True,
        "support_username": "kelbet_support",
        "stars_refunds_enabled": True,
        "stars_reconciliation_enabled": True,
        "stars_refund_user_daily_limit": 10,
        "stars_refund_operator_daily_limit": 10,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _seed_paid(
    session: AsyncSession,
    *,
    telegram_id: int,
    charge_id: str,
    order_key: str,
) -> tuple[UUID, UUID]:
    settings = _settings()
    user, _ = await RegistrationService(
        session, Settings(welcome_credits=5)
    ).register_with_language(
        telegram_id=telegram_id,
        username=f"stars_{telegram_id}",
        language=Language.RU,
    )
    order = await PaymentService(session, settings).create_order(
        user_id=user.id,
        product_slug="starter",
        idempotency_key=order_key,
        terms_accepted=True,
        language=Language.RU,
    )
    completed = await PaymentService(session, settings).complete_payment(
        telegram_id=telegram_id,
        invoice_payload=order.invoice_payload,
        currency="XTR",
        total_amount=order.total_amount,
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id=None,
    )
    assert completed.processed and completed.applied
    return order.id, user.id


async def _seed_operator(session: AsyncSession, telegram_id: int = 939_999) -> UUID:
    user, _ = await RegistrationService(
        session, Settings(welcome_credits=1)
    ).register_with_language(
        telegram_id=telegram_id,
        username="refund_operator",
        language=Language.RU,
    )
    return user.id


def _record(charge_id: str, direction: str, *, amount: int | None = None) -> StarTransactionRecord:
    # Reconciliation matches this against the order total, which comes from the
    # starter pack seed. A literal would silently drift from the catalog.
    if amount is None:
        amount = next(row["stars"] for row in payment_product_rows() if row["slug"] == "starter")
    return StarTransactionRecord(
        transaction_id=charge_id,
        amount=amount,
        occurred_at=datetime.now(UTC),
        direction=direction,  # type: ignore[arg-type]
        partner_type="user",
        transaction_type="invoice_payment",
    )


def test_payment_production_gate_requires_every_explicit_approval_field() -> None:
    incomplete = Settings(
        payments_enabled=True,
        payment_terms_url="http://example.test/draft",
        payment_terms_version="draft",
    )
    assert set(payment_production_gate_failures(incomplete)) == {
        "terms_url_missing",
        "refund_policy_url_missing",
        "terms_version_unapproved",
        "seller_identity_missing",
        "finance_review_missing",
        "support_contact_missing",
    }
    assert payment_production_gate_failures(_settings()) == ()
    assert Settings().payments_enabled is False
    assert Settings().stars_refunds_enabled is False
    assert Settings().stars_reconciliation_enabled is False


@pytest.mark.asyncio
async def test_operator_refund_calls_fake_once_and_reverses_ledger_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings()
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
        order_id, user_id = await _seed_paid(
            session, telegram_id=930_001, charge_id="charge-success", order_key="refund-success"
        )
        operator_id = await _seed_operator(session)
        requested = await PaymentRefundService(session, settings).request_refund(
            order_id=order_id,
            operator_user_id=operator_id,
            operator_reference="case-refund-success",
            reason="buyer_request",
        )
        assert requested.status is PaymentRefundStatus.REQUESTED

    gateway = FakeStarsGateway(refund_outcomes=[True])
    assert await process_due_refund(session_factory, gateway, settings) == 1
    assert await process_due_refund(session_factory, gateway, settings) == 0
    assert gateway.refund_calls == [(930_001, "charge-success")]

    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == user_id))
        ).scalar_one()
        order = await session.get(PaymentOrder, order_id)
        reverse_count = await session.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.reason == TxReason.PAYMENT_REFUND.value)
        )
    assert refund.status == PaymentRefundStatus.REFUNDED.value
    assert refund.external_refunded_at is not None
    assert refund.ledger_transaction_id is not None
    assert wallet.balance == 5
    assert order is not None and order.status == PaymentStatus.REFUNDED.value
    assert reverse_count == 1


@pytest.mark.asyncio
async def test_concurrent_refund_request_is_idempotent_by_charge_and_reference(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings()
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
        order_id, _ = await _seed_paid(
            session,
            telegram_id=930_002,
            charge_id="charge-concurrent",
            order_key="refund-concurrent",
        )
        operator_id = await _seed_operator(session)

    async def request() -> UUID:
        async with session_factory() as session, session.begin():
            result = await PaymentRefundService(session, settings).request_refund(
                order_id=order_id,
                operator_user_id=operator_id,
                operator_reference="case-refund-concurrent",
                reason="buyer_request",
            )
            return result.id

    first, second = await asyncio.gather(request(), request())
    assert first == second
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentRefund)) == 1
    async with session_factory() as session, session.begin():
        with pytest.raises(PaymentRefundConflictError):
            await PaymentRefundService(session, settings).request_refund(
                order_id=order_id,
                operator_user_id=operator_id,
                operator_reference="different-reference",
                reason="buyer_request",
            )


@pytest.mark.asyncio
async def test_timeout_unknown_is_recovered_from_outgoing_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings()
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
        order_id, _ = await _seed_paid(
            session, telegram_id=930_003, charge_id="charge-timeout", order_key="refund-timeout"
        )
        operator_id = await _seed_operator(session)
        await PaymentRefundService(session, settings).request_refund(
            order_id=order_id,
            operator_user_id=operator_id,
            operator_reference="case-refund-timeout",
            reason="buyer_request",
        )

    timeout_gateway = FakeStarsGateway(refund_outcomes=[TimeoutError()])
    assert await process_due_refund(session_factory, timeout_gateway, settings) == 1
    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        assert refund.status == PaymentRefundStatus.NEEDS_REVIEW.value
        assert refund.external_refunded_at is None
        refund_id = refund.id
    async with session_factory() as session, session.begin():
        with pytest.raises(PaymentRefundConflictError, match="must be reconciled"):
            await PaymentRefundService(session, settings).retry_refund(refund_id)

    records = [_record("charge-timeout", "incoming"), _record("charge-timeout", "outgoing")]
    async with session_factory() as session, session.begin():
        assert (await reconcile_star_transactions(session, records, settings=settings)) == 0
    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        assert refund.status == PaymentRefundStatus.REFUNDED.value
        assert refund.ledger_transaction_id is not None


@pytest.mark.asyncio
async def test_external_success_then_db_failure_is_recoverable_by_reconciliation(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
        order_id, _ = await _seed_paid(
            session,
            telegram_id=930_004,
            charge_id="charge-db-failure",
            order_key="refund-db-failure",
        )
        operator_id = await _seed_operator(session)
        await PaymentRefundService(session, settings).request_refund(
            order_id=order_id,
            operator_user_id=operator_id,
            operator_reference="case-refund-db-failure",
            reason="buyer_request",
        )

    original_debit = WalletService.debit

    async def fail_after_external(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated_db_failure")

    monkeypatch.setattr(WalletService, "debit", fail_after_external)
    gateway = FakeStarsGateway(refund_outcomes=[True])
    with pytest.raises(RuntimeError, match="simulated_db_failure"):
        await process_due_refund(session_factory, gateway, settings)
    monkeypatch.setattr(WalletService, "debit", original_debit)

    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        assert refund.status == PaymentRefundStatus.PROCESSING.value
        assert refund.ledger_transaction_id is None

    records = [
        _record("charge-db-failure", "incoming"),
        _record("charge-db-failure", "outgoing"),
    ]
    async with session_factory() as session, session.begin():
        await reconcile_star_transactions(session, records, settings=settings)
    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        assert refund.status == PaymentRefundStatus.REFUNDED.value
        assert refund.ledger_transaction_id is not None
    assert gateway.refund_calls == [(930_004, "charge-db-failure")]


@pytest.mark.asyncio
async def test_transient_failure_retries_but_fraud_limit_never_calls_gateway(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    settings = _settings()
    async with session_factory() as session, session.begin():
        await seed_payment_products(session)
        order_id, _ = await _seed_paid(
            session, telegram_id=930_005, charge_id="charge-retry", order_key="refund-retry"
        )
        operator_id = await _seed_operator(session)
        await PaymentRefundService(session, settings).request_refund(
            order_id=order_id,
            operator_user_id=operator_id,
            operator_reference="case-refund-retry",
            reason="buyer_request",
            now=now,
        )
    gateway = FakeStarsGateway(
        refund_outcomes=[
            StarsGatewayError("telegram_unavailable", transient=True),
            True,
        ]
    )
    assert await process_due_refund(session_factory, gateway, settings, now=now) == 1
    async with session_factory() as session:
        refund = (await session.execute(select(PaymentRefund))).scalar_one()
        assert refund.status == PaymentRefundStatus.FAILED.value
    assert (
        await process_due_refund(
            session_factory, gateway, settings, now=now + timedelta(seconds=31)
        )
        == 1
    )
    assert len(gateway.refund_calls) == 2

    limited = _settings(stars_refund_user_daily_limit=0)
    async with session_factory() as session, session.begin():
        order_id, _ = await _seed_paid(
            session,
            telegram_id=930_006,
            charge_id="charge-fraud-limit",
            order_key="refund-fraud-limit",
        )
        result = await PaymentRefundService(session, limited).request_refund(
            order_id=order_id,
            operator_user_id=operator_id,
            operator_reference="case-refund-fraud-limit",
            reason="buyer_request",
        )
        assert result.status is PaymentRefundStatus.NEEDS_REVIEW
        assert result.last_error_code == "user_daily_limit"
    untouched = FakeStarsGateway()
    assert await process_due_refund(session_factory, untouched, limited) == 0
    assert untouched.refund_calls == []


@pytest.mark.asyncio
async def test_reconciliation_detects_all_supported_discrepancy_classes(
    session: AsyncSession,
) -> None:
    settings = _settings()
    await seed_payment_products(session)
    order_id, _ = await _seed_paid(
        session, telegram_id=930_007, charge_id="charge-disputed", order_key="refund-disputed"
    )
    no_ledger_order_id, _ = await _seed_paid(
        session,
        telegram_id=930_008,
        charge_id="charge-no-ledger",
        order_key="refund-no-ledger",
    )
    no_ledger_order = await session.get(PaymentOrder, no_ledger_order_id)
    assert no_ledger_order is not None
    no_ledger_order.ledger_transaction_id = None
    await session.flush()

    records = [
        _record("unknown-charge", "incoming"),
        _record("duplicate-charge", "incoming"),
        _record("duplicate-charge", "incoming"),
        _record("charge-disputed", "outgoing"),
    ]
    count = await reconcile_star_transactions(session, records, settings=settings)
    kinds = set(
        (
            await session.execute(
                select(PaymentReconciliationIssue.kind).where(
                    PaymentReconciliationIssue.status != "resolved"
                )
            )
        ).scalars()
    )
    assert count == len(
        set(
            (
                await session.execute(
                    select(PaymentReconciliationIssue.issue_key).where(
                        PaymentReconciliationIssue.status != "resolved"
                    )
                )
            ).scalars()
        )
    )
    assert {
        "telegram_without_receipt",
        "duplicate_charge_id",
        "external_reversal",
        "paid_without_ledger",
        "ledger_without_transaction",
    }.issubset(kinds)
    disputed = await session.get(PaymentOrder, order_id)
    assert disputed is not None and disputed.status == PaymentStatus.DISPUTED.value
