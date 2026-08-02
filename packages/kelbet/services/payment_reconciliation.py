from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import (
    PaymentReconciliationIssue,
    PaymentReconciliationRun,
    StarTransactionObservation,
)
from kelbet.domain.enums import (
    PaymentReceiptStatus,
    PaymentReconciliationIssueStatus,
    PaymentStatus,
    StarTransactionDirection,
)
from kelbet.observability import get_metrics
from kelbet.payments.gateway import StarsOperationsGateway, StarTransactionRecord
from kelbet.repositories.payment import PaymentRepository
from kelbet.services.payment import PaymentService, payment_production_gate_failures
from kelbet.services.payment_refund import PaymentRefundService
from kelbet.services.referral import ReferralService

_MAX_TRANSACTIONS_PER_RUN = 10_000


@dataclass(frozen=True, slots=True)
class StarTransactionFetch:
    records: list[StarTransactionRecord]
    coverage_complete: bool
    next_offset: int | None


def _reconciliation_metric(outcome: str) -> None:
    get_metrics().incr("payment.reconciliation", tags={"outcome": outcome})


async def fetch_all_star_transactions(
    gateway: StarsOperationsGateway, settings: Settings
) -> list[StarTransactionRecord]:
    return (await fetch_star_transaction_window(gateway, settings)).records


async def fetch_star_transaction_window(
    gateway: StarsOperationsGateway, settings: Settings
) -> StarTransactionFetch:
    if not settings.stars_reconciliation_enabled:
        return StarTransactionFetch(records=[], coverage_complete=True, next_offset=None)
    if payment_production_gate_failures(settings):
        raise RuntimeError("Telegram Stars production gate is incomplete")
    limit = min(100, max(1, settings.stars_reconciliation_page_limit))
    records: list[StarTransactionRecord] = []
    offset = 0
    coverage_complete = False
    while offset < _MAX_TRANSACTIONS_PER_RUN:
        page = await gateway.get_star_transactions(offset=offset, limit=limit)
        records.extend(page)
        if len(page) < limit:
            coverage_complete = True
            break
        offset += len(page)
    bounded = records[:_MAX_TRANSACTIONS_PER_RUN]
    return StarTransactionFetch(
        records=bounded,
        coverage_complete=coverage_complete,
        next_offset=None if coverage_complete else len(bounded),
    )


async def run_star_reconciliation(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: StarsOperationsGateway,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    if not settings.stars_reconciliation_enabled:
        _reconciliation_metric("disabled")
        return 0
    current = now or datetime.now(UTC)
    try:
        fetched = await fetch_star_transaction_window(gateway, settings)
    except Exception:
        async with session_factory() as session, session.begin():
            session.add(
                PaymentReconciliationRun(
                    status="failed",
                    fetched_count=0,
                    issue_count=0,
                    started_at=current,
                    finished_at=current,
                    error_code="telegram_fetch_failed",
                )
            )
        _reconciliation_metric("failed")
        raise
    async with session_factory() as session, session.begin():
        issue_count = await reconcile_star_transactions(
            session,
            fetched.records,
            settings=settings,
            now=current,
            coverage_complete=fetched.coverage_complete,
            next_offset=fetched.next_offset,
        )
    _reconciliation_metric("issues" if issue_count else "clean")
    return issue_count


async def reconcile_star_transactions(
    session: AsyncSession,
    records: list[StarTransactionRecord],
    *,
    settings: Settings,
    now: datetime | None = None,
    coverage_complete: bool = True,
    next_offset: int | None = None,
) -> int:
    current = now or datetime.now(UTC)
    payments = PaymentRepository(session)
    run = PaymentReconciliationRun(
        status="running",
        fetched_count=len(records),
        issue_count=0,
        coverage_complete=coverage_complete,
        next_offset=next_offset,
        started_at=current,
        finished_at=None,
        error_code=None,
    )
    session.add(run)
    await session.flush()
    active_keys: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()

    for record in records:
        identity = (record.transaction_id, record.direction)
        if identity in seen_keys:
            await _upsert_issue(
                payments,
                session,
                active_keys,
                key=f"duplicate_charge_id:{record.direction}:{record.transaction_id}",
                kind="duplicate_charge_id",
                status=PaymentReconciliationIssueStatus.NEEDS_REVIEW.value,
                severity="critical",
                transaction_id=record.transaction_id,
                details={"direction": record.direction},
                current=current,
            )
            continue
        seen_keys.add(identity)
        observation = await payments.get_observation(record.transaction_id, record.direction)
        if observation is None:
            session.add(
                StarTransactionObservation(
                    telegram_transaction_id=record.transaction_id,
                    direction=record.direction,
                    amount=record.amount,
                    occurred_at=record.occurred_at,
                    partner_type=record.partner_type[:32],
                    transaction_type=(record.transaction_type or "")[:64] or None,
                    telegram_user_id=record.telegram_user_id,
                    invoice_payload=(record.invoice_payload or "")[:128] or None,
                    observed_at=current,
                )
            )
        else:
            observation.amount = record.amount
            observation.occurred_at = record.occurred_at
            observation.partner_type = record.partner_type[:32]
            observation.transaction_type = (record.transaction_type or "")[:64] or None
            observation.telegram_user_id = record.telegram_user_id
            observation.invoice_payload = (record.invoice_payload or "")[:128] or None
            observation.observed_at = current

        receipt = await payments.get_receipt_by_charge_id(record.transaction_id)
        if record.direction == StarTransactionDirection.INCOMING.value:
            if (
                receipt is None
                and record.telegram_user_id is not None
                and record.invoice_payload
            ):
                recovered = await PaymentService(session, settings).complete_payment(
                    telegram_id=record.telegram_user_id,
                    invoice_payload=record.invoice_payload,
                    currency="XTR",
                    total_amount=record.amount,
                    telegram_payment_charge_id=record.transaction_id,
                    provider_payment_charge_id=None,
                    now=record.occurred_at,
                )
                if recovered.processed:
                    receipt = await payments.get_receipt_by_charge_id(record.transaction_id)
            if receipt is None:
                await _upsert_issue(
                    payments,
                    session,
                    active_keys,
                    key=f"telegram_without_receipt:{record.transaction_id}",
                    kind="telegram_without_receipt",
                    status=PaymentReconciliationIssueStatus.OPEN.value,
                    severity="critical",
                    transaction_id=record.transaction_id,
                    details={
                        "amount": record.amount,
                        "recovery_proof": (
                            "missing_user_or_payload"
                            if record.telegram_user_id is None or not record.invoice_payload
                            else "order_snapshot_mismatch"
                        ),
                    },
                    current=current,
                )
            elif receipt.total_amount != record.amount:
                await _upsert_issue(
                    payments,
                    session,
                    active_keys,
                    key=f"transaction_amount_mismatch:{record.transaction_id}",
                    kind="transaction_amount_mismatch",
                    status=PaymentReconciliationIssueStatus.NEEDS_REVIEW.value,
                    severity="critical",
                    order_id=receipt.order_id,
                    transaction_id=record.transaction_id,
                    details={
                        "telegram_amount": record.amount,
                        "receipt_amount": receipt.total_amount,
                    },
                    current=current,
                )
            elif receipt.order_id is not None:
                await session.flush()
                await ReferralService(session, settings).observe_reconciled_purchase(
                    receipt.order_id,
                    now=current,
                )
        else:
            refund = await payments.get_refund_by_charge_id(record.transaction_id, for_update=True)
            order_id = (
                refund.order_id
                if refund is not None
                else receipt.order_id
                if receipt is not None
                else None
            )
            if refund is not None:
                await PaymentRefundService(session, settings).finalize_confirmed_external_refund(
                    refund, observed_at=record.occurred_at
                )
            else:
                if receipt is not None:
                    receipt.status = PaymentReceiptStatus.DISPUTED.value
                    if order_id is not None:
                        order = await payments.get_order_by_id(order_id, for_update=True)
                        if order is not None:
                            order.status = PaymentStatus.DISPUTED.value
                await _upsert_issue(
                    payments,
                    session,
                    active_keys,
                    key=f"external_reversal:{record.transaction_id}",
                    kind="external_reversal",
                    status=PaymentReconciliationIssueStatus.NEEDS_REVIEW.value,
                    severity="critical",
                    order_id=order_id,
                    transaction_id=record.transaction_id,
                    details={
                        "classification": "suspected_chargeback_or_external_refund",
                        "telegram_exposes_explicit_chargeback_type": False,
                    },
                    current=current,
                )
            if order_id is not None:
                await ReferralService(session, settings).observe_payment_reversal(
                    order_id,
                    now=current,
                )

    observations = await payments.list_observations()
    incoming_ids = {
        row.telegram_transaction_id
        for row in observations
        if row.direction == StarTransactionDirection.INCOMING.value
    }
    paid_orders = await payments.list_paid_orders()
    for order in paid_orders:
        receipt = await payments.get_receipt_by_order_id(order.id)
        if order.ledger_transaction_id is None:
            await _upsert_issue(
                payments,
                session,
                active_keys,
                key=f"paid_without_ledger:{order.id}",
                kind="paid_without_ledger",
                status=PaymentReconciliationIssueStatus.OPEN.value,
                severity="critical",
                order_id=order.id,
                details={},
                current=current,
            )
        if receipt is not None and receipt.telegram_payment_charge_id not in incoming_ids:
            await _upsert_issue(
                payments,
                session,
                active_keys,
                key=f"ledger_without_transaction:{order.id}",
                kind="ledger_without_transaction",
                status=PaymentReconciliationIssueStatus.OPEN.value,
                severity="warning",
                order_id=order.id,
                transaction_id=receipt.telegram_payment_charge_id,
                details={},
                current=current,
            )

    for transaction in await payments.list_payment_purchase_transactions():
        charge_id = str((transaction.meta or {}).get("telegram_payment_charge_id") or "")
        if not charge_id or charge_id not in incoming_ids:
            await _upsert_issue(
                payments,
                session,
                active_keys,
                key=f"ledger_without_transaction:tx:{transaction.id}",
                kind="ledger_without_transaction",
                status=PaymentReconciliationIssueStatus.OPEN.value,
                severity="warning",
                details={"ledger_transaction_id": str(transaction.id)},
                current=current,
            )

    for refund in await payments.list_refunds(limit=10_000, offset=0):
        if refund.external_refunded_at is not None and refund.ledger_transaction_id is None:
            await _upsert_issue(
                payments,
                session,
                active_keys,
                key=f"refund_without_reverse_ledger:{refund.id}",
                kind="refund_without_reverse_ledger",
                status=PaymentReconciliationIssueStatus.NEEDS_REVIEW.value,
                severity="critical",
                order_id=refund.order_id,
                refund_id=refund.id,
                transaction_id=refund.payment_charge_id,
                details={"error_code": refund.last_error_code or "reverse_ledger_missing"},
                current=current,
            )

    if coverage_complete:
        for issue in await payments.list_open_issues():
            if issue.issue_key not in active_keys:
                issue.status = PaymentReconciliationIssueStatus.RESOLVED.value
                issue.resolved_at = current
                issue.last_seen_at = current

    run.status = "completed"
    run.issue_count = len(active_keys)
    run.error_code = None if coverage_complete else "telegram_history_truncated"
    run.finished_at = current
    await session.flush()
    return len(active_keys)


async def _upsert_issue(
    payments: PaymentRepository,
    session: AsyncSession,
    active_keys: set[str],
    *,
    key: str,
    kind: str,
    status: str,
    severity: str,
    current: datetime,
    order_id: Any = None,
    refund_id: Any = None,
    transaction_id: str | None = None,
    details: dict[str, Any],
) -> None:
    active_keys.add(key)
    issue = await payments.get_issue(key)
    if issue is None:
        issue = PaymentReconciliationIssue(
            issue_key=key,
            kind=kind,
            status=status,
            severity=severity,
            order_id=order_id,
            refund_id=refund_id,
            telegram_transaction_id=transaction_id,
            details=details,
            first_seen_at=current,
            last_seen_at=current,
            resolved_at=None,
        )
        session.add(issue)
    else:
        issue.kind = kind
        issue.status = status
        issue.severity = severity
        issue.order_id = order_id
        issue.refund_id = refund_id
        issue.telegram_transaction_id = transaction_id
        issue.details = details
        issue.last_seen_at = current
        issue.resolved_at = None
    get_metrics().incr("payment.reconciliation_issue", tags={"kind": kind})
    await session.flush()
