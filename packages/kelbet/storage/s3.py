"""S3-compatible storage (Cloudflare R2 / MinIO) via boto3."""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from kelbet.config import Settings
from kelbet.domain.exceptions import StorageError
from kelbet.storage.base import ObjectHead, PresignedGet, PresignedPut


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_bucket:
            msg = "S3_BUCKET is required for s3 storage backend"
            raise ValueError(msg)
        self._bucket = settings.s3_bucket
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": settings.s3_region or "auto",
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self._client: BaseClient = boto3.client(**kwargs)

    @property
    def backend_name(self) -> str:
        return "r2"

    @property
    def bucket(self) -> str:
        return self._bucket

    async def create_presigned_put(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int,
    ) -> PresignedPut:
        def _sign() -> str:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
            return str(url)

        url = await asyncio.to_thread(_sign)
        return PresignedPut(
            url=url,
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def head_object(self, *, object_key: str) -> ObjectHead:
        def _head() -> dict[str, Any]:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
            return dict(response)

        try:
            response = await asyncio.to_thread(_head)
        except ClientError as exc:
            raise StorageError(f"head_object failed for {object_key}") from exc
        return ObjectHead(
            content_type=response.get("ContentType"),
            content_length=int(response.get("ContentLength") or 0),
            etag=response.get("ETag"),
        )

    async def get_object_prefix(self, *, object_key: str, nbytes: int) -> bytes:
        def _get() -> bytes:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=object_key,
                Range=f"bytes=0-{max(nbytes - 1, 0)}",
            )
            body = response["Body"].read(nbytes)
            return bytes(body)

        try:
            return await asyncio.to_thread(_get)
        except ClientError as exc:
            raise StorageError(f"get_object failed for {object_key}") from exc

    async def get_object(self, *, object_key: str) -> bytes:
        def _get() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
            return bytes(response["Body"].read())

        try:
            return await asyncio.to_thread(_get)
        except ClientError as exc:
            raise StorageError(f"get_object failed for {object_key}") from exc

    async def create_presigned_get(
        self,
        *,
        object_key: str,
        content_type: str,
        download_name: str,
        expires_in: int,
    ) -> PresignedGet:
        def _sign() -> str:
            safe_name = download_name.replace('"', "")
            url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": f'inline; filename="{safe_name}"',
                },
                ExpiresIn=expires_in,
                HttpMethod="GET",
            )
            return str(url)

        try:
            url = await asyncio.to_thread(_sign)
        except ClientError as exc:
            raise StorageError(f"presign get failed for {object_key}") from exc
        return PresignedGet(url=url, expires_in=expires_in)

    async def delete_object(self, *, object_key: str) -> None:
        def _delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)

        try:
            await asyncio.to_thread(_delete)
        except ClientError as exc:
            raise StorageError(f"delete_object failed for {object_key}") from exc
