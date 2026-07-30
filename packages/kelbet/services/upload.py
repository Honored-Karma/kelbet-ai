from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.domain.enums import AssetRole, AssetStatus, RetentionClass
from kelbet.domain.exceptions import AssetNotFoundError, StorageError, UploadValidationError
from kelbet.repositories.asset import AssetRepository
from kelbet.storage import (
    ObjectStorage,
    assert_allowed_content_type,
    assert_size_within_limit,
    build_input_object_key,
    image_dimensions,
    validate_magic_bytes,
)

IMAGE_HEADER_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class PresignUploadResult:
    asset_id: UUID
    upload_url: str
    object_key: str
    headers: dict[str, str]
    expires_in: int
    max_bytes: int


@dataclass(frozen=True, slots=True)
class CompleteUploadResult:
    asset_id: UUID
    status: AssetStatus
    content_type: str
    byte_size: int
    magic_ok: bool
    width: int | None
    height: int | None


class UploadService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings or get_settings()
        self._assets = AssetRepository(session)

    async def create_presigned_upload(
        self,
        *,
        user_id: UUID,
        content_type: str,
        byte_size: int,
        role: AssetRole = AssetRole.INPUT,
        now: datetime | None = None,
    ) -> PresignUploadResult:
        mime = assert_allowed_content_type(content_type)
        assert_size_within_limit(byte_size, max_bytes=self._settings.upload_max_bytes)
        if role not in {AssetRole.INPUT, AssetRole.MASK}:
            raise UploadValidationError(f"Unsupported upload role: {role}")

        current = now or datetime.now(UTC)
        expires_at = current + timedelta(hours=self._settings.upload_temp_ttl_hours)
        # Temporary key until asset id exists; rewritten immediately after insert.
        placeholder_key = f"inputs/{user_id}/pending/{uuid4().hex}.bin"
        asset = await self._assets.create_pending(
            user_id=user_id,
            role=role,
            storage_backend=self._storage.backend_name,
            bucket=self._storage.bucket,
            object_key=placeholder_key,
            content_type=mime,
            declared_byte_size=byte_size,
            retention_class=RetentionClass.TEMP_INPUT,
            expires_at=expires_at,
        )
        object_key = build_input_object_key(
            user_id=user_id,
            asset_id=asset.id,
            content_type=mime,
        )
        asset.object_key = object_key
        await self._assets.save(asset)

        presigned = await self._storage.create_presigned_put(
            object_key=object_key,
            content_type=mime,
            expires_in=self._settings.s3_presign_ttl_seconds,
        )
        return PresignUploadResult(
            asset_id=asset.id,
            upload_url=presigned.url,
            object_key=object_key,
            headers=presigned.headers,
            expires_in=presigned.expires_in,
            max_bytes=self._settings.upload_max_bytes,
        )

    async def complete_upload(
        self,
        *,
        user_id: UUID,
        asset_id: UUID,
    ) -> CompleteUploadResult:
        asset = await self._assets.get_by_id(asset_id)
        if asset is None or asset.user_id != user_id or asset.deleted_at is not None:
            raise AssetNotFoundError(f"Asset {asset_id} not found")
        if asset.status == AssetStatus.READY.value:
            return CompleteUploadResult(
                asset_id=asset.id,
                status=AssetStatus.READY,
                content_type=asset.content_type,
                byte_size=asset.byte_size,
                magic_ok=asset.magic_ok,
                width=asset.width,
                height=asset.height,
            )
        if asset.status not in {AssetStatus.PENDING.value, AssetStatus.REJECTED.value}:
            raise UploadValidationError(f"Asset {asset_id} cannot be completed")

        try:
            head = await self._storage.head_object(object_key=asset.object_key)
        except StorageError as exc:
            asset.status = AssetStatus.REJECTED.value
            asset.reject_reason = "object_missing"
            await self._assets.save(asset)
            raise UploadValidationError("Uploaded object not found in storage") from exc

        if head.content_length <= 0:
            asset.status = AssetStatus.REJECTED.value
            asset.reject_reason = "empty_object"
            await self._assets.save(asset)
            raise UploadValidationError("Uploaded object is empty")

        if head.content_length > self._settings.upload_max_bytes:
            asset.status = AssetStatus.REJECTED.value
            asset.reject_reason = "too_large"
            await self._assets.save(asset)
            raise UploadValidationError("Uploaded object exceeds size limit")

        # Declared size is a hint; actual size must not exceed declared by a large margin
        # and must stay under global max. Allow exact or smaller actual size.
        if head.content_length > asset.declared_byte_size:
            asset.status = AssetStatus.REJECTED.value
            asset.reject_reason = "size_mismatch"
            await self._assets.save(asset)
            raise UploadValidationError("Uploaded object larger than declared size")

        stored_type = (head.content_type or asset.content_type).split(";")[0].strip().lower()
        if stored_type and stored_type != asset.content_type:
            # Some S3 setups omit/alter Content-Type; prefer declared mime + magic check.
            pass

        try:
            header = await self._storage.get_object_prefix(
                object_key=asset.object_key,
                nbytes=IMAGE_HEADER_BYTES,
            )
            validate_magic_bytes(asset.content_type, header)
        except UploadValidationError:
            asset.status = AssetStatus.REJECTED.value
            asset.reject_reason = "magic_mismatch"
            asset.magic_ok = False
            asset.byte_size = head.content_length
            await self._assets.save(asset)
            raise

        asset.byte_size = head.content_length
        asset.magic_ok = True
        asset.status = AssetStatus.READY.value
        asset.reject_reason = None
        dimensions = image_dimensions(asset.content_type, header)
        asset.width = dimensions[0] if dimensions is not None else None
        asset.height = dimensions[1] if dimensions is not None else None
        await self._assets.save(asset)
        return CompleteUploadResult(
            asset_id=asset.id,
            status=AssetStatus.READY,
            content_type=asset.content_type,
            byte_size=asset.byte_size,
            magic_ok=True,
            width=asset.width,
            height=asset.height,
        )
