"""MinIO object storage client (S3-compatible)."""

from functools import lru_cache
from io import BytesIO

from minio import Minio

from app.core.config import get_settings


class ObjectStorage:
    """Thin wrapper around the MinIO client for document files.

    The methods are synchronous (the MinIO SDK is sync); call them from a
    thread when inside async code (e.g. `starlette.concurrency.run_in_threadpool`).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist yet."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put_object(self, object_name: str, data: bytes, content_type: str) -> str:
        """Store bytes under ``object_name`` and return that name."""
        self.ensure_bucket()
        self._client.put_object(
            self._bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def get_object(self, object_name: str) -> bytes:
        """Return the bytes stored under ``object_name``."""
        response = self._client.get_object(self._bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def remove_object(self, object_name: str) -> None:
        """Delete an object (ignored if missing)."""
        self._client.remove_object(self._bucket, object_name)


@lru_cache
def get_object_storage() -> ObjectStorage:
    """Return a cached ObjectStorage instance."""
    return ObjectStorage()
