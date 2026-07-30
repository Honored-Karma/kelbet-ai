from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from apps.api.deps import get_access_token, get_auth_service, get_current_user, rate_limit_auth
from kelbet.services.auth import AuthService, SessionUser

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=8192)


class AuthUserResponse(BaseModel):
    id: str
    telegram_id: int
    language: str
    plan: str


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: AuthUserResponse
    welcome_applied: bool


class LogoutResponse(BaseModel):
    revoked: bool


@router.post("/telegram", response_model=TelegramAuthResponse)
async def auth_telegram(
    body: TelegramAuthRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    _: None = Depends(rate_limit_auth),
) -> TelegramAuthResponse:
    user_agent = request.headers.get("user-agent")
    result = await auth_service.login_with_init_data(
        body.init_data,
        user_agent=user_agent[:512] if user_agent else None,
    )
    return TelegramAuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
        welcome_applied=result.welcome_applied,
        user=AuthUserResponse(
            id=str(result.user_id),
            telegram_id=result.telegram_id,
            language=result.language.value,
            plan=result.plan,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
async def auth_logout(
    _current: SessionUser = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    revoked = await auth_service.logout(access_token)
    return LogoutResponse(revoked=revoked)
