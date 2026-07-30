"""In-memory object storage for tests and local development."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from urllib.parse import quote

from kelbet.domain.exceptions import StorageError
from kelbet.storage.base import ObjectHead, PresignedGet, PresignedPut


@dataclass
class _StoredObject:
    data: bytes
    content_type: str


@dataclass
class MemoryObjectStorage:
    bucket_name: str = "kelbet-assets"
    objects: dict[str, _StoredObject] = field(default_factory=dict)

    @property
    def backend_name(self) -> str:
        return "memory"

    @property
    def bucket(self) -> str:
        return self.bucket_name

    async def create_presigned_put(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int,
    ) -> PresignedPut:
        url = f"memory://{self.bucket_name}/{quote(object_key, safe='/')}"
        return PresignedPut(
            url=url,
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    def put_bytes(self, object_key: str, data: bytes, *, content_type: str) -> None:
        """Test helper: simulate client PUT after presign."""
        self.objects[object_key] = _StoredObject(data=data, content_type=content_type)

    async def head_object(self, *, object_key: str) -> ObjectHead:
        obj = self.objects.get(object_key)
        if obj is None:
            raise StorageError(f"Object not found: {object_key}")
        return ObjectHead(
            content_type=obj.content_type,
            content_length=len(obj.data),
        )

    async def get_object_prefix(self, *, object_key: str, nbytes: int) -> bytes:
        obj = self.objects.get(object_key)
        if obj is None:
            raise StorageError(f"Object not found: {object_key}")
        return obj.data[:nbytes]

    async def create_presigned_get(
        self,
        *,
        object_key: str,
        content_type: str,
        download_name: str,
        expires_in: int,
    ) -> PresignedGet:
        del download_name
        obj = self.objects.get(object_key)
        if obj is None:
            raise StorageError(f"Object not found: {object_key}")
        encoded = base64.b64encode(obj.data).decode("ascii")
        return PresignedGet(
            url=f"data:{content_type};base64,{encoded}",
            expires_in=expires_in,
        )

    async def delete_object(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)
