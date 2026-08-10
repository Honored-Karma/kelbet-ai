from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import TelegramUpdateInbox

PROCESSING = "processing"
PROCESSED = "processed"
FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ClaimedTelegramUpdate:
    update_id: int
    event_type: str
    payload: dict[str, Any]
    attempt_count: int


def _retry_at(attempt_count: int, now: datetime) -> datetime:
    delay_seconds = min(2 ** min(attempt_count, 8), 300)
    return now + timedelta(seconds=delay_seconds)


class TelegramUpdateInboxService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_delivery(
        self,
        *,
        update_id: int,
        event_type: str,
        payload: dict[str, Any],
        stale_after_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> bool:
        moment = now or datetime.now(UTC)
        statement = (
            insert(TelegramUpdateInbox)
            .values(
                update_id=update_id,
                event_type=event_type,
                payload=payload,
                status=PROCESSING,
                attempt_count=1,
                claimed_at=moment,
                next_attempt_at=None,
                processed_at=None,
                last_error_code=None,
            )
            .on_conflict_do_nothing(index_elements=[TelegramUpdateInbox.update_id])
            .returning(TelegramUpdateInbox.id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is not None:
            return True

        row = (
            await self._session.execute(
                select(TelegramUpdateInbox)
                .where(TelegramUpdateInbox.update_id == update_id)
                .with_for_update()
            )
        ).scalar_one()
        stale_before = moment - timedelta(seconds=stale_after_seconds)
        retry_due = row.status == FAILED and (
            row.next_attempt_at is None or row.next_attempt_at <= moment
        )
        abandoned = row.status == PROCESSING and row.claimed_at <= stale_before
        if row.status == PROCESSED or row.attempt_count >= max_attempts:
            return False
        if not retry_due and not abandoned:
            return False

        row.status = PROCESSING
        row.attempt_count += 1
        row.claimed_at = moment
        row.next_attempt_at = None
        row.last_error_code = None
        return True

    async def mark_processed(self, update_id: int, *, now: datetime | None = None) -> None:
        row = await self._for_update(update_id)
        if row is None:
            return
        row.status = PROCESSED
        row.processed_at = now or datetime.now(UTC)
        row.next_attempt_at = None
        row.last_error_code = None

    async def mark_failed(
        self,
        update_id: int,
        *,
        error_code: str = "handler_error",
        now: datetime | None = None,
    ) -> None:
        moment = now or datetime.now(UTC)
        row = await self._for_update(update_id)
        if row is None or row.status == PROCESSED:
            return
        row.status = FAILED
        row.next_attempt_at = _retry_at(row.attempt_count, moment)
        row.last_error_code = error_code[:64]

    async def claim_due(
        self,
        *,
        limit: int,
        stale_after_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> list[ClaimedTelegramUpdate]:
        moment = now or datetime.now(UTC)
        stale_before = moment - timedelta(seconds=stale_after_seconds)
        due = or_(
            and_(
                TelegramUpdateInbox.status == FAILED,
                or_(
                    TelegramUpdateInbox.next_attempt_at.is_(None),
                    TelegramUpdateInbox.next_attempt_at <= moment,
                ),
            ),
            and_(
                TelegramUpdateInbox.status == PROCESSING,
                TelegramUpdateInbox.claimed_at <= stale_before,
            ),
        )
        rows = (
            (
                await self._session.execute(
                    select(TelegramUpdateInbox)
                    .where(due, TelegramUpdateInbox.attempt_count < max_attempts)
                    .order_by(TelegramUpdateInbox.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        claimed: list[ClaimedTelegramUpdate] = []
        for row in rows:
            row.status = PROCESSING
            row.attempt_count += 1
            row.claimed_at = moment
            row.next_attempt_at = None
            row.last_error_code = None
            claimed.append(
                ClaimedTelegramUpdate(
                    update_id=row.update_id,
                    event_type=row.event_type,
                    payload=dict(row.payload),
                    attempt_count=row.attempt_count,
                )
            )
        return claimed

    async def _for_update(self, update_id: int) -> TelegramUpdateInbox | None:
        return (
            await self._session.execute(
                select(TelegramUpdateInbox)
                .where(TelegramUpdateInbox.update_id == update_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
