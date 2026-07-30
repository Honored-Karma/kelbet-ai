from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_chat_provider,
    get_current_user,
    get_db_session,
    get_settings_dep,
    rate_limit_prompt_assistant,
)
from kelbet.chat import ChatProvider
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.services.auth import SessionUser
from kelbet.services.prompt_assistant import PromptAssistantService, PromptIntent

router = APIRouter(prefix="/prompt-assistant", tags=["prompt-assistant"])


class PromptAssistantConfigResponse(BaseModel):
    credit_cost: int
    max_input_chars: int
    max_output_chars: int
    charge_policy: Literal["on_success"] = "on_success"


class ImprovePromptRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=8000)
    target_language: Language | None = None
    intent: PromptIntent = "general"


class ImprovePromptResponse(BaseModel):
    improved_prompt: str
    language: Language
    credit_cost: int
    charged: bool
    balance: int
    limits: dict[str, int]


@router.get("/config", response_model=PromptAssistantConfigResponse)
async def prompt_assistant_config(
    _: SessionUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
) -> PromptAssistantConfigResponse:
    return PromptAssistantConfigResponse(
        credit_cost=settings.prompt_assistant_credit_cost,
        max_input_chars=settings.prompt_assistant_max_input_chars,
        max_output_chars=settings.prompt_assistant_max_output_chars,
    )


@router.post("/improve", response_model=ImprovePromptResponse)
async def improve_prompt(
    body: ImprovePromptRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: ChatProvider = Depends(get_chat_provider),
    settings: Settings = Depends(get_settings_dep),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _: None = Depends(rate_limit_prompt_assistant),
) -> ImprovePromptResponse:
    result = await PromptAssistantService(session, provider, settings).improve(
        user_id=current.user_id,
        brief=body.brief,
        request_id=idempotency_key.strip(),
        target_language=body.target_language,
        intent=body.intent,
    )
    return ImprovePromptResponse(
        improved_prompt=result.improved_prompt,
        language=result.language,
        credit_cost=result.credit_cost,
        charged=result.charged,
        balance=result.balance,
        limits={
            "max_input_chars": result.max_input_chars,
            "max_output_chars": result.max_output_chars,
        },
    )
