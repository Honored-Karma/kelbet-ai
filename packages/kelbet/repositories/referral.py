from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import ReferralAttribution, ReferralCode, ReferralReward


class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_code_for_user(self, user_id: UUID) -> ReferralCode | None:
        row = await self._session.execute(
            select(ReferralCode).where(ReferralCode.user_id == user_id)
        )
        return row.scalar_one_or_none()

    async def get_code(self, code: str) -> ReferralCode | None:
        row = await self._session.execute(select(ReferralCode).where(ReferralCode.code == code))
        return row.scalar_one_or_none()

    async def create_code(self, *, user_id: UUID, code: str) -> ReferralCode:
        row = ReferralCode(user_id=user_id, code=code)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_attribution_for_invited(
        self, invited_user_id: UUID, *, for_update: bool = False
    ) -> ReferralAttribution | None:
        statement = select(ReferralAttribution).where(
            ReferralAttribution.invited_user_id == invited_user_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_attribution(
        self, attribution_id: UUID, *, for_update: bool = False
    ) -> ReferralAttribution | None:
        statement = select(ReferralAttribution).where(ReferralAttribution.id == attribution_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def create_attribution(
        self,
        *,
        code: ReferralCode,
        invited_user_id: UUID,
        now: datetime,
        inviter_bonus_credits: int,
        invitee_bonus_credits: int,
    ) -> tuple[ReferralAttribution, ReferralReward]:
        attribution = ReferralAttribution(
            referral_code_id=code.id,
            inviter_user_id=code.user_id,
            invited_user_id=invited_user_id,
            attributed_at=now,
        )
        self._session.add(attribution)
        await self._session.flush()
        reward = ReferralReward(
            attribution_id=attribution.id,
            status="pending",
            inviter_bonus_credits=inviter_bonus_credits,
            invitee_bonus_credits=invitee_bonus_credits,
        )
        self._session.add(reward)
        await self._session.flush()
        return attribution, reward

    async def get_reward_for_attribution(
        self, attribution_id: UUID, *, for_update: bool = False
    ) -> ReferralReward | None:
        statement = select(ReferralReward).where(ReferralReward.attribution_id == attribution_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def get_reward_for_payment(
        self, payment_order_id: UUID, *, for_update: bool = False
    ) -> ReferralReward | None:
        statement = select(ReferralReward).where(
            ReferralReward.payment_order_id == payment_order_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.execute(statement)
        return row.scalar_one_or_none()

    async def count_attributions_since(self, inviter_user_id: UUID, since: datetime) -> int:
        value = await self._session.execute(
            select(func.count())
            .select_from(ReferralAttribution)
            .where(
                ReferralAttribution.inviter_user_id == inviter_user_id,
                ReferralAttribution.attributed_at >= since,
            )
        )
        return int(value.scalar_one())

    async def claim_due_reward(self, now: datetime) -> ReferralReward | None:
        row = await self._session.execute(
            select(ReferralReward)
            .where(
                ReferralReward.status == "eligible",
                ReferralReward.eligible_at.is_not(None),
                ReferralReward.eligible_at <= now,
            )
            .order_by(ReferralReward.eligible_at, ReferralReward.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def lock_inviter_day(self, inviter_user_id: UUID, day: str) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:value))"),
            {"value": f"referral:{inviter_user_id}:{day}"},
        )

    async def count_credited_for_inviter_since(self, inviter_user_id: UUID, since: datetime) -> int:
        value = await self._session.execute(
            select(func.count())
            .select_from(ReferralReward)
            .join(
                ReferralAttribution,
                ReferralAttribution.id == ReferralReward.attribution_id,
            )
            .where(
                ReferralAttribution.inviter_user_id == inviter_user_id,
                ReferralReward.status == "credited",
                ReferralReward.credited_at >= since,
            )
        )
        return int(value.scalar_one())

    async def summary_for_inviter(self, inviter_user_id: UUID) -> dict[str, int]:
        values = await self._session.execute(
            select(
                func.count(ReferralAttribution.id),
                func.count(ReferralReward.id).filter(
                    ReferralReward.status.in_(["pending", "eligible"])
                ),
                func.count(ReferralReward.id).filter(ReferralReward.status == "credited"),
                func.coalesce(
                    func.sum(ReferralReward.inviter_bonus_credits).filter(
                        ReferralReward.status == "credited"
                    ),
                    0,
                ),
            )
            .select_from(ReferralAttribution)
            .join(
                ReferralReward,
                ReferralReward.attribution_id == ReferralAttribution.id,
                isouter=True,
            )
            .where(ReferralAttribution.inviter_user_id == inviter_user_id)
        )
        invited, pending, credited, credits = values.one()
        return {
            "invited_count": int(invited or 0),
            "pending_rewards_count": int(pending or 0),
            "credited_rewards_count": int(credited or 0),
            "credited_bonus_credits": int(credits or 0),
        }

    async def list_for_operator(
        self, *, status: str | None, limit: int, offset: int
    ) -> list[tuple[ReferralReward, ReferralAttribution]]:
        statement = select(ReferralReward, ReferralAttribution).join(
            ReferralAttribution,
            ReferralAttribution.id == ReferralReward.attribution_id,
        )
        if status is not None:
            statement = statement.where(ReferralReward.status == status)
        rows = await self._session.execute(
            statement.order_by(ReferralReward.created_at.desc(), ReferralReward.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.tuples().all())
