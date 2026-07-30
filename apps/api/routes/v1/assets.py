from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_object_storage, get_settings_dep
from kelbet.config import Settings
from kelbet.services.asset import AssetService
from kelbet.services.auth import SessionUser
from kelbet.storage import ObjectStorage

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetDownloadResponse(BaseModel):
    id: str
    role: str
    content_type: str
    byte_size: int
    width: int | None
    height: int | None
    download_url: str
    expires_in: int


class AssetDownloadsRequest(BaseModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=20)


class AssetDownloadsResponse(BaseModel):
    items: list[AssetDownloadResponse]


def _response(asset: object) -> AssetDownloadResponse:
    from kelbet.services.asset import AssetDownloadDTO

    assert isinstance(asset, AssetDownloadDTO)
    return AssetDownloadResponse(
        id=str(asset.id),
        role=asset.role.value,
        content_type=asset.content_type,
        byte_size=asset.byte_size,
        width=asset.width,
        height=asset.height,
        download_url=asset.download_url,
        expires_in=asset.expires_in,
    )


@router.post("/downloads", response_model=AssetDownloadsResponse)
async def get_assets(
    body: AssetDownloadsRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    settings: Settings = Depends(get_settings_dep),
) -> AssetDownloadsResponse:
    assets = await AssetService(session, storage, settings).get_downloads(
        user_id=current.user_id,
        asset_ids=body.asset_ids,
    )
    return AssetDownloadsResponse(items=[_response(asset) for asset in assets])


@router.get("/{asset_id}", response_model=AssetDownloadResponse)
async def get_asset(
    asset_id: UUID,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    settings: Settings = Depends(get_settings_dep),
) -> AssetDownloadResponse:
    asset = await AssetService(session, storage, settings).get_download(
        user_id=current.user_id,
        asset_id=asset_id,
    )
    return _response(asset)
