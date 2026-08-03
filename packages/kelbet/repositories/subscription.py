from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import Subscription, SubscriptionPeriod, SubscriptionPlan
from kelbet.domain.enums import SubscriptionStatus

LIVE_STATUSES = (
    SubscriptionStatus.PENDING.value,
    SubscriptionStatus.ACTIVE.value,
    SubscriptionStatus.CANCELLED.value,
    SubscriptionStatus.PAYMENT_FAILED.value,
)


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_plans(self) -> list[SubscriptionPlan]:
        rows = await self._session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.enabled.is_(True))
            .order_by(SubscriptionPlan.display_order, SubscriptionPlan.slug)
        )
        return list(rows.scalars())

    async def get_plan_by_slug(self, slug: str) -> SubscriptionPlan | None:
        row = await self._session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.slug == slug)
        )
        return row.scalar_one_or_none()

    async def get_plan_by_id(self, plan_id: UUID) -> SubscriptionPlan | None:
        row = await self._session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        return row.scalar_one_or_none()

    async def get_live_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> Subscription | None:
        """The user's one non-terminal subscription, if any.

        A partial unique index guarantees there is at most one, so `scalar_one_or_none`
        here is an assertion about the schema, not an optimistic assumption.
        """
        statement = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(LIVE_STATUSES),
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_by_payload(
        self, invoice_payload: str, *, for_update: bool = False
    ) -> Subscription | None:
        statement = select(Subscription).where(Subscription.invoice_payload == invoice_payload)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_by_id(
        self, subscription_id: UUID, *, for_update: bool = False
    ) -> Subscription | None:
        statement = select(Subscription).where(Subscription.id == subscription_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_period_by_charge_id(self, charge_id: str) -> SubscriptionPeriod | None:
        row = await self._session.execute(
            select(SubscriptionPeriod).where(SubscriptionPeriod.charge_id == charge_id)
        )
        return row.scalar_one_or_none()

    async def list_periods(
        self, subscription_id: UUID, *, limit: int = 24
    ) -> list[SubscriptionPeriod]:
        rows = await self._session.execute(
            select(SubscriptionPeriod)
            .where(SubscriptionPeriod.subscription_id == subscription_id)
            .order_by(SubscriptionPeriod.period_start.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def claim_expired(self, now: datetime) -> Subscription | None:
        """Take one subscription whose paid period has run out, locking it for this worker.

        `skip_locked` is what makes two concurrent workers safe: the second skips the row
        the first is holding instead of blocking on it or processing it twice.
        """
        row = await self._session.execute(
            select(Subscription)
            .where(
                Subscription.status.in_(
                    (
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.CANCELLED.value,
                        SubscriptionStatus.PAYMENT_FAILED.value,
                    )
                ),
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end <= now,
            )
            .order_by(Subscription.current_period_end, Subscription.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return row.scalar_one_or_none()
