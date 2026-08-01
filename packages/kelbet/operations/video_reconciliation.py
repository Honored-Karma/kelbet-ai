"""Financial and lifecycle reconciliation for a staging batch of video jobs."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import (
    CreditReservation,
    CreditTransaction,
    GenerationAsset,
    GenerationAttempt,
    GenerationJob,
    ProviderUsage,
)
from kelbet.domain.enums import (
    AssetRole,
    AssetStatus,
    AttemptStatus,
    GenerationStatus,
    ReservationStatus,
    TxReason,
)
from kelbet.services.wallet import capture_idempotency_key

_TERMINAL = {
    GenerationStatus.SUCCEEDED,
    GenerationStatus.FAILED,
    GenerationStatus.CANCELLED,
    GenerationStatus.TIMED_OUT,
    GenerationStatus.DEAD_LETTER,
}
_NON_SUCCESS_TERMINAL = _TERMINAL - {GenerationStatus.SUCCEEDED}


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    code: str
    generation_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class VideoReconciliationReport:
    passed: bool
    generated_at: str
    since: str
    minimum_jobs: int
    selected_jobs: int
    terminal_jobs: int
    active_jobs: int
    status_counts: dict[str, int]
    provider_counts: dict[str, int]
    user_credits_expected: int
    user_credits_captured: int
    user_credits_released: int
    provider_cost_units: int
    issues: list[ReconciliationIssue]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


async def reconcile_video_jobs(
    session: AsyncSession,
    *,
    since: datetime,
    minimum_jobs: int = 100,
    limit: int = 1_000,
    maximum_active_age: timedelta = timedelta(minutes=35),
    require_all_terminal: bool = True,
    now: datetime | None = None,
) -> VideoReconciliationReport:
    current = now or datetime.now(UTC)
    jobs = list(
        (
            await session.execute(
                select(GenerationJob)
                .where(
                    GenerationJob.modality == "video",
                    GenerationJob.created_at >= since,
                )
                .order_by(GenerationJob.created_at, GenerationJob.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    job_ids = [job.id for job in jobs]
    reservations = await _by_generation(
        session,
        CreditReservation,
        CreditReservation.generation_id,
        job_ids,
    )
    usages = await _group_by_generation(
        session,
        ProviderUsage,
        ProviderUsage.generation_id,
        job_ids,
    )
    attempts = await _group_by_generation(
        session,
        GenerationAttempt,
        GenerationAttempt.generation_id,
        job_ids,
    )
    assets = await _group_by_generation(
        session,
        GenerationAsset,
        GenerationAsset.generation_id,
        job_ids,
    )
    capture_ids = [
        reservation.capture_tx_id
        for reservation in reservations.values()
        if reservation.capture_tx_id is not None
    ]
    transactions = {
        row.id: row
        for row in (
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.id.in_(capture_ids))
                )
            )
            .scalars()
            .all()
            if capture_ids
            else []
        )
    }

    issues: list[ReconciliationIssue] = []
    if len(jobs) < minimum_jobs:
        issues.append(
            ReconciliationIssue(
                code="minimum_job_count",
                generation_id=None,
                message=f"Expected at least {minimum_jobs} video jobs, found {len(jobs)}",
            )
        )

    status_counts = Counter(job.status for job in jobs)
    provider_counts = Counter(job.provider for job in jobs)
    terminal_jobs = sum(status_counts[status.value] for status in _TERMINAL)
    active_jobs = len(jobs) - terminal_jobs
    if require_all_terminal and active_jobs:
        issues.append(
            ReconciliationIssue(
                code="non_terminal_jobs",
                generation_id=None,
                message=f"Expected a terminal batch, found {active_jobs} active video jobs",
            )
        )
    expected_credits = 0
    captured_credits = 0
    released_credits = 0
    provider_cost_units = 0
    seen_capture_transactions: set[UUID] = set()

    for job in jobs:
        generation_id = str(job.id)
        status = GenerationStatus(job.status)
        reservation = reservations.get(job.id)
        job_usages = usages.get(job.id, [])
        job_attempts = attempts.get(job.id, [])
        job_assets = assets.get(job.id, [])
        provider_cost_units += sum(usage.provider_cost_units for usage in job_usages)

        if reservation is None or job.reservation_id != reservation.id:
            issues.append(
                ReconciliationIssue(
                    code="reservation_missing",
                    generation_id=generation_id,
                    message="Generation is not linked to its credit reservation",
                )
            )
            continue

        snapshot_price = reservation.quote_snapshot.get("user_credit_price")
        if reservation.amount != job.user_credit_price or snapshot_price != job.user_credit_price:
            issues.append(
                ReconciliationIssue(
                    code="quoted_price_changed",
                    generation_id=generation_id,
                    message="Job, reservation and quote snapshot prices differ",
                )
            )

        for usage in job_usages:
            if usage.user_credit_price != job.user_credit_price:
                issues.append(
                    ReconciliationIssue(
                        code="usage_price_mismatch",
                        generation_id=generation_id,
                        message="Provider usage does not preserve the quoted user price",
                    )
                )
            if usage.provider in {"runway", "google"} and usage.provider_cost_units <= 0:
                issues.append(
                    ReconciliationIssue(
                        code="provider_cost_missing",
                        generation_id=generation_id,
                        message="Production provider usage has no positive cost estimate",
                    )
                )

        if status in _TERMINAL:
            if (job.provider_job_id is not None or job_attempts) and not job_usages:
                issues.append(
                    ReconciliationIssue(
                        code="provider_usage_missing",
                        generation_id=generation_id,
                        message="Terminal video job has no provider usage record",
                    )
                )
            if job.finished_at is None or job.next_poll_at is not None:
                issues.append(
                    ReconciliationIssue(
                        code="terminal_state_incomplete",
                        generation_id=generation_id,
                        message="Terminal job must have finished_at and no next_poll_at",
                    )
                )
        elif current - job.created_at > maximum_active_age:
            issues.append(
                ReconciliationIssue(
                    code="lost_active_job",
                    generation_id=generation_id,
                    message="Active job exceeded the allowed reconciliation age",
                )
            )

        if status is GenerationStatus.SUCCEEDED:
            expected_credits += job.user_credit_price
            if reservation.status != ReservationStatus.CAPTURED.value:
                issues.append(
                    ReconciliationIssue(
                        code="success_not_captured",
                        generation_id=generation_id,
                        message="Successful job does not have a captured reservation",
                    )
                )
            else:
                captured_credits += reservation.amount
            if reservation.finalized_at is None:
                issues.append(
                    ReconciliationIssue(
                        code="captured_reservation_not_finalized",
                        generation_id=generation_id,
                        message="Successful reservation has no finalized timestamp",
                    )
                )
            _check_capture_transaction(
                reservation,
                transactions,
                seen_capture_transactions,
                issues,
                generation_id,
            )
            ready_outputs = [
                asset
                for asset in job_assets
                if asset.role == AssetRole.OUTPUT.value
                and asset.status == AssetStatus.READY.value
                and asset.content_type.startswith("video/")
                and asset.deleted_at is None
            ]
            if not ready_outputs:
                issues.append(
                    ReconciliationIssue(
                        code="video_output_missing",
                        generation_id=generation_id,
                        message="Successful video job has no ready video output asset",
                    )
                )
            successful_usages = [
                usage
                for usage in job_usages
                if isinstance(usage.meta, dict) and usage.meta.get("status") == "succeeded"
            ]
            successful_attempts = [
                attempt
                for attempt in job_attempts
                if attempt.status == AttemptStatus.SUCCEEDED.value
            ]
            if len(successful_usages) != 1 or len(successful_attempts) != 1:
                issues.append(
                    ReconciliationIssue(
                        code="success_accounting_cardinality",
                        generation_id=generation_id,
                        message="Successful job must have exactly one successful attempt and usage",
                    )
                )
        elif status in _NON_SUCCESS_TERMINAL:
            if reservation.status not in {
                ReservationStatus.RELEASED.value,
                ReservationStatus.EXPIRED.value,
            }:
                issues.append(
                    ReconciliationIssue(
                        code="failed_reservation_held",
                        generation_id=generation_id,
                        message="Non-successful terminal job did not release its reservation",
                    )
                )
            else:
                released_credits += reservation.amount
            if reservation.finalized_at is None:
                issues.append(
                    ReconciliationIssue(
                        code="released_reservation_not_finalized",
                        generation_id=generation_id,
                        message="Non-successful terminal reservation is not finalized",
                    )
                )
        elif reservation.status != ReservationStatus.HELD.value:
            issues.append(
                ReconciliationIssue(
                    code="active_reservation_not_held",
                    generation_id=generation_id,
                    message="Active job must keep its reservation held",
                )
            )
        elif (
            reservation.capture_tx_id is not None
            or reservation.refund_tx_id is not None
            or reservation.finalized_at is not None
        ):
            issues.append(
                ReconciliationIssue(
                    code="active_reservation_already_finalized",
                    generation_id=generation_id,
                    message="Active job reservation contains terminal financial fields",
                )
            )

    return VideoReconciliationReport(
        passed=not issues,
        generated_at=current.isoformat(),
        since=since.isoformat(),
        minimum_jobs=minimum_jobs,
        selected_jobs=len(jobs),
        terminal_jobs=terminal_jobs,
        active_jobs=active_jobs,
        status_counts=dict(sorted(status_counts.items())),
        provider_counts=dict(sorted(provider_counts.items())),
        user_credits_expected=expected_credits,
        user_credits_captured=captured_credits,
        user_credits_released=released_credits,
        provider_cost_units=provider_cost_units,
        issues=issues,
    )


async def _by_generation(
    session: AsyncSession,
    model: type[Any],
    generation_column: Any,
    job_ids: list[UUID],
) -> dict[UUID, Any]:
    if not job_ids:
        return {}
    rows = (
        (await session.execute(select(model).where(generation_column.in_(job_ids)))).scalars().all()
    )
    return {row.generation_id: row for row in rows}


async def _group_by_generation(
    session: AsyncSession,
    model: type[Any],
    generation_column: Any,
    job_ids: list[UUID],
) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    if not job_ids:
        return grouped
    rows = (
        (await session.execute(select(model).where(generation_column.in_(job_ids)))).scalars().all()
    )
    for row in rows:
        if row.generation_id is not None:
            grouped[row.generation_id].append(row)
    return grouped


def _check_capture_transaction(
    reservation: CreditReservation,
    transactions: dict[UUID, CreditTransaction],
    seen: set[UUID],
    issues: list[ReconciliationIssue],
    generation_id: str,
) -> None:
    transaction_id = reservation.capture_tx_id
    transaction = transactions.get(transaction_id) if transaction_id is not None else None
    if transaction is None:
        issues.append(
            ReconciliationIssue(
                code="capture_transaction_missing",
                generation_id=generation_id,
                message="Captured reservation has no capture ledger transaction",
            )
        )
        return
    if transaction.id in seen:
        issues.append(
            ReconciliationIssue(
                code="capture_transaction_reused",
                generation_id=generation_id,
                message="Capture transaction is linked to multiple video jobs",
            )
        )
    seen.add(transaction.id)
    if (
        transaction.amount != -reservation.amount
        or transaction.reason != TxReason.GENERATION_CAPTURE.value
        or transaction.idempotency_key != capture_idempotency_key(reservation.id)
    ):
        issues.append(
            ReconciliationIssue(
                code="capture_transaction_invalid",
                generation_id=generation_id,
                message="Capture ledger amount, reason or idempotency key is invalid",
            )
        )
