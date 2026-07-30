from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models.asset import GenerationAsset
from kelbet.domain.enums import AssetRole, AssetStatus
from kelbet.domain.exceptions import AssetNotFoundError, StorageError
from kelbet.repositories.asset import AssetRepository
from kelbet.storage import ObjectStorage, image_dimensions

IMAGE_HEADER_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class AssetDownloadDTO:
    id: UUID
    role: AssetRole
    content_type: str
    byte_size: int
    width: int | None
    height: int | None
    download_url: str
    expires_in: int


class AssetService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        settings: Settings | None = None,
    ) -> None:
        self._assets = AssetRepository(session)
        self._storage = storage
        self._settings = settings or get_settings()

    async def _hydrate_dimensions(self, asset: GenerationAsset) -> None:
        if asset.width is not None and asset.height is not None:
            return
        if not asset.content_type.startswith("image/"):
            return
        try:
            prefix = await self._storage.get_object_prefix(
                object_key=asset.object_key,
                nbytes=IMAGE_HEADER_BYTES,
            )
        except StorageError:
            return
        dimensions = image_dimensions(asset.content_type, prefix)
        if dimensions is not None:
            asset.width, asset.height = dimensions

    async def get_download(
        self,
        *,
        user_id: UUID,
        asset_id: UUID,
    ) -> AssetDownloadDTO:
        asset = await self._assets.get_by_id(asset_id)
        current = datetime.now(UTC)
        if (
            asset is None
            or asset.user_id != user_id
            or asset.deleted_at is not None
            or asset.status != AssetStatus.READY.value
            or (asset.expires_at is not None and asset.expires_at <= current)
        ):
            raise AssetNotFoundError(f"Asset {asset_id} not found")

        suffix = PurePosixPath(asset.object_key).suffix
        await self._hydrate_dimensions(asset)
        download_name = f"kelbet-{asset.id}{suffix}"
        signed = await self._storage.create_presigned_get(
            object_key=asset.object_key,
            content_type=asset.content_type,
            download_name=download_name,
            expires_in=self._settings.s3_presign_ttl_seconds,
        )
        return AssetDownloadDTO(
            id=asset.id,
            role=AssetRole(asset.role),
            content_type=asset.content_type,
            byte_size=asset.byte_size,
            width=asset.width,
            height=asset.height,
            download_url=signed.url,
            expires_in=signed.expires_in,
        )

    async def get_downloads(
        self,
        *,
        user_id: UUID,
        asset_ids: list[UUID],
        now: datetime | None = None,
    ) -> list[AssetDownloadDTO]:
        if len(asset_ids) > 20:
            raise ValueError("At most 20 assets can be requested")
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Duplicate asset ids are not allowed")
        current = now or datetime.now(UTC)
        assets = await self._assets.list_ready_owned(
            user_id=user_id,
            asset_ids=asset_ids,
            now=current,
        )
        downloads: list[AssetDownloadDTO] = []
        for asset in assets:
            await self._hydrate_dimensions(asset)
            suffix = PurePosixPath(asset.object_key).suffix
            signed = await self._storage.create_presigned_get(
                object_key=asset.object_key,
                content_type=asset.content_type,
                download_name=f"kelbet-{asset.id}{suffix}",
                expires_in=self._settings.s3_presign_ttl_seconds,
            )
            downloads.append(
                AssetDownloadDTO(
                    id=asset.id,
                    role=AssetRole(asset.role),
                    content_type=asset.content_type,
                    byte_size=asset.byte_size,
                    width=asset.width,
                    height=asset.height,
                    download_url=signed.url,
                    expires_in=signed.expires_in,
                )
            )
        return downloads
