from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models.asset import GenerationAsset
from kelbet.domain.enums import AssetRole, AssetStatus, RetentionClass


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        user_id: UUID,
        role: AssetRole,
        storage_backend: str,
        bucket: str,
        object_key: str,
        content_type: str,
        declared_byte_size: int,
        retention_class: RetentionClass,
        expires_at: datetime | None,
    ) -> GenerationAsset:
        # object_key is set after we know asset id — create with placeholder then update
        asset = GenerationAsset(
            user_id=user_id,
            role=role.value,
            status=AssetStatus.PENDING.value,
            storage_backend=storage_backend,
            bucket=bucket,
            object_key=object_key,
            content_type=content_type,
            byte_size=0,
            declared_byte_size=declared_byte_size,
            magic_ok=False,
            visibility="private",
            retention_class=retention_class.value,
            expires_at=expires_at,
        )
        self._session.add(asset)
        await self._session.flush()
        return asset

    async def get_by_id(self, asset_id: UUID) -> GenerationAsset | None:
        result = await self._session.execute(
            select(GenerationAsset).where(GenerationAsset.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def list_ready_owned(
        self,
        *,
        user_id: UUID,
        asset_ids: list[UUID],
        now: datetime,
    ) -> list[GenerationAsset]:
        if not asset_ids:
            return []
        result = await self._session.execute(
            select(GenerationAsset).where(
                GenerationAsset.id.in_(asset_ids),
                GenerationAsset.user_id == user_id,
                GenerationAsset.status == AssetStatus.READY.value,
                GenerationAsset.deleted_at.is_(None),
                or_(
                    GenerationAsset.expires_at.is_(None),
                    GenerationAsset.expires_at > now,
                ),
            )
        )
        by_id = {asset.id: asset for asset in result.scalars().all()}
        return [by_id[asset_id] for asset_id in asset_ids if asset_id in by_id]

    async def save(self, asset: GenerationAsset) -> GenerationAsset:
        await self._session.flush()
        return asset
