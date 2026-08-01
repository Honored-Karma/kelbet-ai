from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import ModerationDecision, UserConsent
from kelbet.domain.enums import ModerationOutcome, ModerationReviewStatus


class ModerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_decision(
        self, *, user_id: UUID, context: str, idempotency_key: str
    ) -> ModerationDecision | None:
        result = await self._session.execute(
            select(ModerationDecision).where(
                ModerationDecision.user_id == user_id,
                ModerationDecision.context == context,
                ModerationDecision.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def create_decision(self, **values: object) -> ModerationDecision:
        row = ModerationDecision(**values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def count_recent_requests(self, user_id: UUID, *, since: datetime) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(ModerationDecision)
            .where(
                ModerationDecision.user_id == user_id,
                ModerationDecision.created_at >= since,
            )
        )
        return int(count or 0)

    async def count_recent_violations(
        self, user_id: UUID, *, hours: int, now: datetime | None = None
    ) -> int:
        current = now or datetime.now(UTC)
        count = await self._session.scalar(
            select(func.count())
            .select_from(ModerationDecision)
            .where(
                ModerationDecision.user_id == user_id,
                ModerationDecision.created_at >= current - timedelta(hours=hours),
                ModerationDecision.outcome.in_(
                    [ModerationOutcome.REPORT.value, ModerationOutcome.BLOCK.value]
                ),
                ~ModerationDecision.reason_codes.contained_by(
                    ["provider_unavailable", "moderation_rate_limit"]
                ),
            )
        )
        return int(count or 0)

    async def bind_generation(self, decision: ModerationDecision, generation_id: UUID) -> None:
        decision.generation_id = generation_id
        await self._session.flush()

    async def list_queue(
        self,
        *,
        review_status: ModerationReviewStatus,
        limit: int,
        offset: int,
    ) -> list[ModerationDecision]:
        result = await self._session.execute(
            select(ModerationDecision)
            .where(
                ModerationDecision.review_status == review_status.value,
                ModerationDecision.outcome.in_(
                    [ModerationOutcome.REPORT.value, ModerationOutcome.BLOCK.value]
                ),
            )
            .order_by(ModerationDecision.created_at.desc(), ModerationDecision.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_for_update(self, decision_id: UUID) -> ModerationDecision | None:
        result = await self._session.execute(
            select(ModerationDecision).where(ModerationDecision.id == decision_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_consent(
        self, *, user_id: UUID, consent_type: str, idempotency_key: str
    ) -> UserConsent | None:
        result = await self._session.execute(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.consent_type == consent_type,
                UserConsent.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def create_consent(self, **values: object) -> UserConsent:
        row = UserConsent(**values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def bind_consent_generation(self, consent: UserConsent, generation_id: UUID) -> None:
        consent.generation_id = generation_id
        await self._session.flush()
