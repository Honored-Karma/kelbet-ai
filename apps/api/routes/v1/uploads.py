from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_object_storage, get_settings_dep
from kelbet.config import Settings
from kelbet.domain.enums import AssetRole
from kelbet.services.auth import SessionUser
from kelbet.services.upload import UploadService
from kelbet.storage import ObjectStorage

router = APIRouter(prefix="/uploads", tags=["uploads"])


class PresignRequest(BaseModel):
    content_type: str = Field(min_length=3, max_length=128)
    byte_size: int = Field(gt=0)
    role: AssetRole = AssetRole.INPUT


class PresignResponse(BaseModel):
    asset_id: str
    upload_url: str
    object_key: str
    headers: dict[str, str]
    expires_in: int
    max_bytes: int


class CompleteResponse(BaseModel):
    asset_id: str
    status: str
    content_type: str
    byte_size: int
    magic_ok: bool
    width: int | None
    height: int | None


@router.post("/presign", response_model=PresignResponse)
async def presign_upload(
    body: PresignRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    settings: Settings = Depends(get_settings_dep),
) -> PresignResponse:
    result = await UploadService(session, storage, settings).create_presigned_upload(
        user_id=current.user_id,
        content_type=body.content_type,
        byte_size=body.byte_size,
        role=body.role,
    )
    return PresignResponse(
        asset_id=str(result.asset_id),
        upload_url=result.upload_url,
        object_key=result.object_key,
        headers=result.headers,
        expires_in=result.expires_in,
        max_bytes=result.max_bytes,
    )


@router.post("/{asset_id}/complete", response_model=CompleteResponse)
async def complete_upload(
    asset_id: str,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    settings: Settings = Depends(get_settings_dep),
) -> CompleteResponse:
    from uuid import UUID

    result = await UploadService(session, storage, settings).complete_upload(
        user_id=current.user_id,
        asset_id=UUID(asset_id),
    )
    return CompleteResponse(
        asset_id=str(result.asset_id),
        status=result.status.value,
        content_type=result.content_type,
        byte_size=result.byte_size,
        magic_ok=result.magic_ok,
        width=result.width,
        height=result.height,
    )
