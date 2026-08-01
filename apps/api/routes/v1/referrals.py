from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_settings_dep
from kelbet.config import Settings
from kelbet.services.auth import SessionUser
from kelbet.services.referral import ReferralService

router = APIRouter(prefix="/referrals", tags=["referrals"])


class ReferralSummaryResponse(BaseModel):
    enabled: bool
    code: str | None
    link: str | None
    invited_count: int
    pending_rewards_count: int
    credited_rewards_count: int
    credited_bonus_credits: int
    inviter_bonus_credits: int
    invitee_bonus_credits: int
    minimum_purchase_stars: int
    waiting_period_hours: int


@router.get("/me", response_model=ReferralSummaryResponse)
async def get_my_referral_summary(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> ReferralSummaryResponse:
    summary = await ReferralService(session, settings).get_summary(current.user_id)
    return ReferralSummaryResponse(
        enabled=summary.enabled,
        code=summary.code,
        link=summary.link,
        invited_count=summary.invited_count,
        pending_rewards_count=summary.pending_rewards_count,
        credited_rewards_count=summary.credited_rewards_count,
        credited_bonus_credits=summary.credited_bonus_credits,
        inviter_bonus_credits=summary.inviter_bonus_credits,
        invitee_bonus_credits=summary.invitee_bonus_credits,
        minimum_purchase_stars=summary.minimum_purchase_stars,
        waiting_period_hours=summary.waiting_period_hours,
    )
