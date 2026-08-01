from fastapi import APIRouter
from pydantic import BaseModel

from kelbet.config import get_settings

router = APIRouter(prefix="/moderation", tags=["moderation"])


class ModerationConfigResponse(BaseModel):
    mode: str
    policy_version: str
    photo_rights_consent_version: str
    support_route: str
    image_moderation_supported: bool


@router.get("/config", response_model=ModerationConfigResponse)
async def get_moderation_config() -> ModerationConfigResponse:
    settings = get_settings()
    return ModerationConfigResponse(
        mode=settings.moderation_mode,
        policy_version=settings.moderation_policy_version,
        photo_rights_consent_version=settings.photo_rights_consent_version,
        support_route="/support",
        image_moderation_supported=False,
    )
