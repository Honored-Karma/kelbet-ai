from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_generation_queue, get_settings_dep
from kelbet.config import Settings
from kelbet.domain.enums import GenerationStatus
from kelbet.queue import GenerationQueue
from kelbet.services.auth import SessionUser
from kelbet.services.generation import GenerationService

router = APIRouter(tags=["history"])


class HistoryItem(BaseModel):
    id: str
    status: GenerationStatus
    modality: str
    model_slug: str | None
    user_credit_price: int
    progress_pct: int
    output_asset_ids: list[str]
    created_at: str
    preview_asset_id: str | None
    preview_content_type: str | None


class HistoryResponse(BaseModel):
    items: list[HistoryItem]


@router.get("/history", response_model=HistoryResponse)
async def history(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> HistoryResponse:
    items = await GenerationService(session, queue, settings).list_history(
        user_id=current.user_id, limit=limit, offset=offset
    )
    return HistoryResponse(
        items=[
            HistoryItem(
                id=str(item.id),
                status=item.status,
                modality=item.modality,
                model_slug=item.model_slug,
                user_credit_price=item.user_credit_price,
                progress_pct=item.progress_pct,
                output_asset_ids=[str(x) for x in item.output_asset_ids],
                created_at=item.created_at.isoformat(),
                preview_asset_id=(
                    str(item.preview_asset_id) if item.preview_asset_id else None
                ),
                preview_content_type=item.preview_content_type,
            )
            for item in items
        ]
    )
