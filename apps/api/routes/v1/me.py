from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session
from kelbet.domain.enums import Language
from kelbet.services.auth import SessionUser
from kelbet.services.profile import ProfileService

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    id: str
    telegram_id: int
    username: str | None
    language: str
    plan: str
    balance: int
    reserved: int
    available: int
    notify_generation_ready: bool


class PatchMeRequest(BaseModel):
    language: Language | None = Field(default=None)
    notify_generation_ready: bool | None = Field(default=None)


@router.get("/me", response_model=MeResponse)
async def get_me(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MeResponse:
    profile = await ProfileService(session).get_profile_by_user_id(current.user_id)
    return MeResponse(
        id=str(profile.user_id),
        telegram_id=profile.telegram_id,
        username=profile.username,
        language=profile.language.value,
        plan=profile.plan.value,
        balance=profile.balance,
        reserved=profile.reserved,
        available=profile.available,
        notify_generation_ready=profile.notify_generation_ready,
    )


@router.patch("/me", response_model=MeResponse)
async def patch_me(
    body: PatchMeRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MeResponse:
    service = ProfileService(session)
    if body.language is not None:
        profile = await service.update_language(current.user_id, body.language)
    else:
        profile = await service.get_profile_by_user_id(current.user_id)
    if body.notify_generation_ready is not None:
        profile = await service.update_generation_notifications(
            current.user_id,
            body.notify_generation_ready,
        )
    return MeResponse(
        id=str(profile.user_id),
        telegram_id=profile.telegram_id,
        username=profile.username,
        language=profile.language.value,
        plan=profile.plan.value,
        balance=profile.balance,
        reserved=profile.reserved,
        available=profile.available,
        notify_generation_ready=profile.notify_generation_ready,
    )
