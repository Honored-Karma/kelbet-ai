from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models.notification import NotificationOutbox
from kelbet.db.models.user import User


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue_generation_ready(
        self,
        *,
        user_id: UUID,
        generation_id: UUID,
        now: datetime,
    ) -> bool:
        user_result = await self._session.execute(
            select(User.notify_generation_ready).where(User.id == user_id)
        )
        enabled = user_result.scalar_one_or_none()
        if enabled is not True:
            return False

        statement = (
            insert(NotificationOutbox)
            .values(
                user_id=user_id,
                generation_id=generation_id,
                channel="telegram",
                event_type="generation_ready",
                status="pending",
                attempts=0,
                next_attempt_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_notification_outbox_generation_event")
            .returning(NotificationOutbox.id)
        )
        inserted = await self._session.execute(statement)
        return inserted.scalar_one_or_none() is not None

    async def count_for_generation(self, generation_id: UUID) -> int:
        result = await self._session.execute(
            select(NotificationOutbox.id).where(NotificationOutbox.generation_id == generation_id)
        )
        return len(list(result.scalars().all()))
