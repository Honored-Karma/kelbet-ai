from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings, stars_canary_id_set
from kelbet.db.models import PaymentReconciliationIssue, PaymentRefund
from kelbet.domain.enums import (
    PaymentReceiptStatus,
    PaymentReconciliationIssueStatus,
    PaymentRefundStatus,
    PaymentStatus,
    TxReason,
)
from kelbet.domain.exceptions import (
    InsufficientCreditsError,
    PaymentOrderNotFoundError,
    PaymentRefundConflictError,
    PaymentRefundNotFoundError,
    PaymentRefundUnavailableError,
    WalletNotFoundError,
)
from kelbet.observability import get_metrics
from kelbet.payments.gateway import StarsGatewayError, StarsOperationsGateway
from kelbet.repositories.payment import PaymentRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.payment import payment_production_gate_failures
from kelbet.services.wallet import WalletService

_RETRY_DELAYS = (timedelta(seconds=30), timedelta(minutes=5), timedelta(minutes=30))


@dataclass(frozen=True, slots=True)
class PaymentRefundDTO:
    id: UUID
    order_id: UUID
    status: PaymentRefundStatus
    stars_amount: int
    credits_amount: int
    attempt_count: int
    external_refunded_at: datetime | None
    ledger_transaction_id: UUID | None
    last_error_code: str | None
    requested_at: datetime
    finished_at: datetime | None


def _metric(status: str) -> None:
    get_metrics().incr("payment.refund", tags={"status": status})


class PaymentRefundService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._payments = PaymentRepository(session)
        self._wallets = WalletRepository(session)

    def _assert_gate(self, telegram_user_id: int) -> None:
        if not self._settings.stars_refunds_enabled:
            raise PaymentRefundUnavailableError("Telegram Stars refunds are disabled")
        failures = payment_production_gate_failures(self._settings)
        if failures:
            raise PaymentRefundUnavailableError("Telegram Stars production gate is incomplete")
        canary_ids = stars_canary_id_set(self._settings)
        if canary_ids and telegram_user_id not in canary_ids:
            raise PaymentRefundUnavailableError("Buyer is outside the Stars canary")

    async def request_refund(
        self,
        *,
        order_id: UUID,
        operator_user_id: UUID,
        operator_reference: str,
        reason: str,
        now: datetime | None = None,
    ) -> PaymentRefundDTO:
        current = now or datetime.now(UTC)
        order = await self._payments.get_order_by_id(order_id, for_update=True)
        if order is None:
            raise PaymentOrderNotFoundError(f"Payment order {order_id} not found")
        receipt = await self._payments.get_receipt_by_order_id(order.id)
        if receipt is None or receipt.status != PaymentReceiptStatus.PROCESSED.value:
            raise PaymentRefundConflictError("Only a processed Stars receipt can be refunded")
        self._assert_gate(receipt.telegram_user_id)

        existing = await self._payments.get_refund_by_order_id(order.id, for_update=True)
        if existing is not None:
            if (
                existing.operator_reference != operator_reference
                or existing.reason != reason
                or existing.operator_user_id != operator_user_id
            ):
                raise PaymentRefundConflictError("Payment charge already has a refund request")
            return self.dto(existing)
        by_reference = await self._payments.get_refund_by_reference(operator_reference)
        if by_reference is not None:
            raise PaymentRefundConflictError("Operator reference was used for another refund")
        if order.status != PaymentStatus.PAID.value:
            raise PaymentRefundConflictError("Only a paid order can be refunded")

        day_start = current - timedelta(days=1)
        user_count = await self._payments.count_refunds_since(
            day_start, telegram_user_id=receipt.telegram_user_id
        )
        operator_count = await self._payments.count_refunds_since(
            day_start, operator_user_id=operator_user_id
        )
        review_code: str | None = None
        if user_count >= self._settings.stars_refund_user_daily_limit:
            review_code = "user_daily_limit"
        elif operator_count >= self._settings.stars_refund_operator_daily_limit:
            review_code = "operator_daily_limit"

        wallet = await self._wallets.get_by_user_id(order.user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for order {order.id} not found")
        if wallet.available < order.credits:
            review_code = "insufficient_reversible_credits"

        refund = PaymentRefund(
            order_id=order.id,
            receipt_id=receipt.id,
            payment_charge_id=receipt.telegram_payment_charge_id,
            telegram_user_id=receipt.telegram_user_id,
            operator_user_id=operator_user_id,
            operator_reference=operator_reference,
            reason=reason,
            status=(
                PaymentRefundStatus.NEEDS_REVIEW.value
                if review_code
                else PaymentRefundStatus.REQUESTED.value
            ),
            stars_amount=order.total_amount,
            credits_amount=order.credits,
            attempt_count=0,
            requested_at=current,
            processing_started_at=None,
            next_attempt_at=None,
            external_refunded_at=None,
            ledger_transaction_id=None,
            last_error_code=review_code,
            finished_at=None,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(refund)
                await self._session.flush()
        except IntegrityError:
            existing = await self._payments.get_refund_by_order_id(order.id)
            if existing is None:
                raise
            if existing.operator_reference != operator_reference:
                raise PaymentRefundConflictError(
                    "Concurrent refund request used another reference"
                ) from None
            refund = existing
        _metric(refund.status)
        return self.dto(refund)

    async def retry_refund(self, refund_id: UUID) -> PaymentRefundDTO:
        refund = await self._payments.get_refund_by_id(refund_id, for_update=True)
        if refund is None:
            raise PaymentRefundNotFoundError(f"Payment refund {refund_id} not found")
        if refund.status not in {
            PaymentRefundStatus.FAILED.value,
            PaymentRefundStatus.NEEDS_REVIEW.value,
        }:
            raise PaymentRefundConflictError("Refund is not retryable")
        if refund.external_refunded_at is not None:
            await self._finalize_ledger(refund, datetime.now(UTC))
        else:
            if refund.last_error_code in {
                "telegram_timeout_unknown",
                "telegram_result_unknown",
            }:
                latest_run = await self._payments.latest_reconciliation_run()
                outgoing = await self._payments.get_observation(
                    refund.payment_charge_id, "outgoing"
                )
                if outgoing is not None:
                    await self.finalize_confirmed_external_refund(
                        refund, observed_at=outgoing.occurred_at
                    )
                    return self.dto(refund)
                if (
                    latest_run is None
                    or latest_run.status != "completed"
                    or latest_run.finished_at is None
                    or refund.processing_started_at is None
                    or latest_run.finished_at <= refund.processing_started_at
                ):
                    raise PaymentRefundConflictError(
                        "Unknown Telegram result must be reconciled before retry"
                    )
            order = await self._payments.get_order_by_id(refund.order_id, for_update=True)
            if order is None:
                raise PaymentOrderNotFoundError(f"Payment order {refund.order_id} not found")
            wallet = await self._wallets.get_by_user_id(order.user_id)
            if wallet is None:
                raise WalletNotFoundError(f"Wallet for order {order.id} not found")
            if wallet.available < refund.credits_amount:
                raise PaymentRefundConflictError("Purchased credits are not currently reversible")
            current = datetime.now(UTC)
            since = current - timedelta(days=1)
            user_count = await self._payments.count_refunds_since(
                since, telegram_user_id=refund.telegram_user_id
            )
            operator_count = await self._payments.count_refunds_since(
                since, operator_user_id=refund.operator_user_id
            )
            if user_count > self._settings.stars_refund_user_daily_limit:
                raise PaymentRefundConflictError("User refund limit still requires review")
            if operator_count > self._settings.stars_refund_operator_daily_limit:
                raise PaymentRefundConflictError("Operator refund limit still requires review")
            refund.status = PaymentRefundStatus.REQUESTED.value
            refund.next_attempt_at = None
            refund.last_error_code = None
            refund.finished_at = None
            await self._session.flush()
        _metric(refund.status)
        return self.dto(refund)

    async def finalize_confirmed_external_refund(
        self, refund: PaymentRefund, *, observed_at: datetime
    ) -> PaymentRefundDTO:
        refund.external_refunded_at = refund.external_refunded_at or observed_at
        await self._finalize_ledger(refund, observed_at)
        return self.dto(refund)

    async def _finalize_ledger(self, refund: PaymentRefund, current: datetime) -> None:
        if refund.ledger_transaction_id is not None:
            refund.status = PaymentRefundStatus.REFUNDED.value
            refund.last_error_code = None
            refund.finished_at = refund.finished_at or current
            await self._session.flush()
            return
        order = await self._payments.get_order_by_id(refund.order_id, for_update=True)
        receipt = await self._payments.get_receipt_by_order_id(refund.order_id)
        if order is None or receipt is None:
            await self._needs_review(refund, "refund_source_missing", current)
            return
        wallet = await self._wallets.get_by_user_id(order.user_id)
        if wallet is None:
            await self._needs_review(refund, "wallet_missing", current)
            return
        try:
            debit = await WalletService(self._session).debit(
                wallet.id,
                refund.credits_amount,
                TxReason.PAYMENT_REFUND,
                f"stars-refund:{refund.payment_charge_id}",
                meta={
                    "payment_order_id": str(order.id),
                    "payment_refund_id": str(refund.id),
                    "stars": refund.stars_amount,
                    "source": "telegram_stars_refund",
                },
            )
        except InsufficientCreditsError:
            await self._needs_review(refund, "reverse_ledger_insufficient", current)
            return
        refund.ledger_transaction_id = debit.transaction_id
        refund.status = PaymentRefundStatus.REFUNDED.value
        refund.last_error_code = None
        refund.finished_at = current
        order.status = PaymentStatus.REFUNDED.value
        order.refunded_at = order.refunded_at or current
        receipt.status = PaymentReceiptStatus.REFUNDED.value
        await self._session.flush()
        _metric("refunded")

    async def _needs_review(
        self, refund: PaymentRefund, error_code: str, current: datetime
    ) -> None:
        refund.status = PaymentRefundStatus.NEEDS_REVIEW.value
        refund.last_error_code = error_code
        refund.finished_at = current
        issue_key = f"refund_without_reverse_ledger:{refund.id}"
        issue = await self._payments.get_issue(issue_key)
        if issue is None:
            self._session.add(
                PaymentReconciliationIssue(
                    issue_key=issue_key,
                    kind="refund_without_reverse_ledger",
                    status=PaymentReconciliationIssueStatus.NEEDS_REVIEW.value,
                    severity="critical",
                    order_id=refund.order_id,
                    refund_id=refund.id,
                    telegram_transaction_id=refund.payment_charge_id,
                    details={"error_code": error_code},
                    first_seen_at=current,
                    last_seen_at=current,
                    resolved_at=None,
                )
            )
        else:
            issue.status = PaymentReconciliationIssueStatus.NEEDS_REVIEW.value
            issue.last_seen_at = current
            issue.details = {"error_code": error_code}
            issue.resolved_at = None
        await self._session.flush()
        _metric("needs_review")

    @staticmethod
    def dto(refund: PaymentRefund) -> PaymentRefundDTO:
        return PaymentRefundDTO(
            id=refund.id,
            order_id=refund.order_id,
            status=PaymentRefundStatus(refund.status),
            stars_amount=refund.stars_amount,
            credits_amount=refund.credits_amount,
            attempt_count=refund.attempt_count,
            external_refunded_at=refund.external_refunded_at,
            ledger_transaction_id=refund.ledger_transaction_id,
            last_error_code=refund.last_error_code,
            requested_at=refund.requested_at,
            finished_at=refund.finished_at,
        )


async def process_due_refund(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: StarsOperationsGateway,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    """Claim, call Telegram outside a DB transaction, then durably compensate."""

    current = now or datetime.now(UTC)
    async with session_factory() as session, session.begin():
        payments = PaymentRepository(session)
        stale_before = current - timedelta(
            seconds=max(30, settings.stars_refund_processing_timeout_seconds)
        )
        stale = await payments.claim_stale_processing_refund(stale_before)
        if stale is not None:
            stale.status = PaymentRefundStatus.NEEDS_REVIEW.value
            stale.last_error_code = "telegram_result_unknown"
            stale.finished_at = current
            _metric("needs_review")
        refund = await payments.claim_due_refund(current)
        if refund is None:
            return 0
        refund.status = PaymentRefundStatus.PROCESSING.value
        refund.attempt_count += 1
        refund.processing_started_at = current
        refund.next_attempt_at = None
        refund_id = refund.id
        telegram_user_id = refund.telegram_user_id
        charge_id = refund.payment_charge_id
        attempt_count = refund.attempt_count
        _metric("processing")

    try:
        refunded = await gateway.refund_star_payment(telegram_user_id, charge_id)
        if not refunded:
            raise StarsGatewayError("telegram_refund_rejected", transient=False)
    except StarsGatewayError as exc:
        await _record_gateway_failure(
            session_factory,
            refund_id,
            code=exc.code,
            transient=exc.transient,
            outcome_unknown=exc.outcome_unknown,
            attempt_count=attempt_count,
            settings=settings,
            current=current,
        )
        return 1
    except TimeoutError:
        await _record_gateway_failure(
            session_factory,
            refund_id,
            code="telegram_timeout_unknown",
            transient=True,
            outcome_unknown=True,
            attempt_count=attempt_count,
            settings=settings,
            current=current,
        )
        return 1
    except Exception:
        await _record_gateway_failure(
            session_factory,
            refund_id,
            code="telegram_result_unknown",
            transient=True,
            outcome_unknown=True,
            attempt_count=attempt_count,
            settings=settings,
            current=current,
        )
        return 1

    async with session_factory() as session, session.begin():
        payments = PaymentRepository(session)
        refund = await payments.get_refund_by_id(refund_id, for_update=True)
        if refund is None:
            raise PaymentRefundNotFoundError(f"Payment refund {refund_id} disappeared")
        await PaymentRefundService(session, settings).finalize_confirmed_external_refund(
            refund, observed_at=current
        )
    return 1


async def _record_gateway_failure(
    session_factory: async_sessionmaker[AsyncSession],
    refund_id: UUID,
    *,
    code: str,
    transient: bool,
    outcome_unknown: bool,
    attempt_count: int,
    settings: Settings,
    current: datetime,
) -> None:
    async with session_factory() as session, session.begin():
        refund = await PaymentRepository(session).get_refund_by_id(refund_id, for_update=True)
        if refund is None:
            raise PaymentRefundNotFoundError(f"Payment refund {refund_id} disappeared")
        retry_limit = max(1, settings.stars_refund_retry_limit)
        if outcome_unknown or not transient or attempt_count >= retry_limit:
            refund.status = PaymentRefundStatus.NEEDS_REVIEW.value
            refund.finished_at = current
        else:
            refund.status = PaymentRefundStatus.FAILED.value
            delay = _RETRY_DELAYS[min(attempt_count - 1, len(_RETRY_DELAYS) - 1)]
            refund.next_attempt_at = current + delay
        refund.last_error_code = code[:64]
        await session.flush()
        _metric(refund.status)
