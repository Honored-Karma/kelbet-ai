from kelbet.config import Settings
from kelbet.storage.base import ObjectStorage
from kelbet.storage.memory import MemoryObjectStorage
from kelbet.storage.s3 import S3ObjectStorage


def build_object_storage(settings: Settings) -> ObjectStorage:
    backend = settings.storage_backend.strip().lower()
    if backend in {"memory", "mock", "fake"}:
        return MemoryObjectStorage(bucket_name=settings.s3_bucket or "kelbet-assets")
    if backend in {"s3", "r2", "minio"}:
        return S3ObjectStorage(settings)
    msg = f"Unknown storage backend: {settings.storage_backend}"
    raise ValueError(msg)
