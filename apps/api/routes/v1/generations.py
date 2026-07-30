from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_current_user,
    get_db_session,
    get_generation_queue,
    get_settings_dep,
    rate_limit_generations,
)
from kelbet.config import Settings
from kelbet.domain.enums import GenerationStatus
from kelbet.queue import GenerationQueue
from kelbet.services.auth import SessionUser
from kelbet.services.generation import GenerationService

router = APIRouter(prefix="/generations", tags=["generations"])


class CreateGenerationRequest(BaseModel):
    quote_id: UUID
    prompt: str = Field(default="", max_length=8000)
    input_asset_ids: list[UUID] = Field(default_factory=list)


class GenerationResponse(BaseModel):
    id: str
    status: GenerationStatus
    modality: str
    model_slug: str | None
    user_credit_price: int
    progress_pct: int
    progress_stage: str | None
    error_code: str | None
    cancelable: bool
    reservation_id: str | None
    output_asset_ids: list[str]
    created_at: str
    eta_seconds: int | None
    estimated_remaining_seconds: int | None


class GenerationDraftResponse(BaseModel):
    source_generation_id: str
    mode: Literal["repeat", "remix", "upscale"]
    model_slug: str | None
    modality: str
    prompt: str
    params: dict[str, Any]
    input_asset_ids: list[str]
    unavailable_asset_ids: list[str]
    missing_input_assets: int
    model_available: bool
    replacement_slug: str | None


def _to_response(dto: object) -> GenerationResponse:
    from kelbet.services.generation import GenerationDTO

    assert isinstance(dto, GenerationDTO)
    return GenerationResponse(
        id=str(dto.id),
        status=dto.status,
        modality=dto.modality,
        model_slug=dto.model_slug,
        user_credit_price=dto.user_credit_price,
        progress_pct=dto.progress_pct,
        progress_stage=dto.progress_stage,
        error_code=dto.error_code,
        cancelable=dto.cancelable,
        reservation_id=str(dto.reservation_id) if dto.reservation_id else None,
        output_asset_ids=[str(x) for x in dto.output_asset_ids],
        created_at=dto.created_at.isoformat(),
        eta_seconds=dto.eta_seconds,
        estimated_remaining_seconds=dto.estimated_remaining_seconds,
    )


@router.post("", response_model=GenerationResponse, status_code=201)
async def create_generation(
    body: CreateGenerationRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _: None = Depends(rate_limit_generations),
) -> GenerationResponse:
    dto = await GenerationService(session, queue, settings).create(
        user_id=current.user_id,
        telegram_id=current.telegram_id,
        idempotency_key=idempotency_key.strip(),
        quote_id=body.quote_id,
        prompt=body.prompt,
        input_asset_ids=body.input_asset_ids,
    )
    return _to_response(dto)


@router.get("/{generation_id}/draft", response_model=GenerationDraftResponse)
async def get_generation_draft(
    generation_id: UUID,
    mode: Literal["repeat", "remix", "upscale"] = "repeat",
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
) -> GenerationDraftResponse:
    draft = await GenerationService(session, queue, settings).get_draft(
        user_id=current.user_id,
        telegram_id=current.telegram_id,
        generation_id=generation_id,
        mode=mode,
    )
    return GenerationDraftResponse(
        source_generation_id=str(draft.source_generation_id),
        mode=draft.mode,
        model_slug=draft.model_slug,
        modality=draft.modality,
        prompt=draft.prompt,
        params=draft.params,
        input_asset_ids=[str(asset_id) for asset_id in draft.input_asset_ids],
        unavailable_asset_ids=[str(asset_id) for asset_id in draft.unavailable_asset_ids],
        missing_input_assets=draft.missing_input_assets,
        model_available=draft.model_available,
        replacement_slug=draft.replacement_slug,
    )


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: UUID,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
) -> GenerationResponse:
    dto = await GenerationService(session, queue, settings).get(
        user_id=current.user_id, generation_id=generation_id
    )
    return _to_response(dto)


@router.post("/{generation_id}/cancel", response_model=GenerationResponse)
async def cancel_generation(
    generation_id: UUID,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
) -> GenerationResponse:
    dto = await GenerationService(session, queue, settings).cancel(
        user_id=current.user_id, generation_id=generation_id
    )
    return _to_response(dto)
