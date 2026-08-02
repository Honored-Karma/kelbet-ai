"""Object storage port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectHead:
    content_type: str | None
    content_length: int
    etag: str | None = None


@dataclass(frozen=True, slots=True)
class PresignedPut:
    url: str
    headers: dict[str, str]
    expires_in: int


@dataclass(frozen=True, slots=True)
class PresignedGet:
    url: str
    expires_in: int


class ObjectStorage(Protocol):
    @property
    def backend_name(self) -> str: ...

    @property
    def bucket(self) -> str: ...

    async def create_presigned_put(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int,
    ) -> PresignedPut: ...

    async def head_object(self, *, object_key: str) -> ObjectHead: ...

    async def get_object_prefix(self, *, object_key: str, nbytes: int) -> bytes: ...

    async def get_object(self, *, object_key: str) -> bytes: ...

    async def create_presigned_get(
        self,
        *,
        object_key: str,
        content_type: str,
        download_name: str,
        expires_in: int,
    ) -> PresignedGet: ...

    async def delete_object(self, *, object_key: str) -> None: ...
