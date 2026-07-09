"""Upload use case: store the file in MinIO and register the document."""

from pathlib import Path
from uuid import UUID, uuid4

from starlette.concurrency import run_in_threadpool

from app.infrastructure.storage.minio import ObjectStorage
from app.modules.documents.application.document_service import DocumentService
from app.modules.documents.domain.upload_validation import validate_document_upload
from app.modules.documents.infrastructure.models import Document
from app.modules.documents.infrastructure.repository import (
    DocumentFormatRepository,
)


class UploadService:
    """Stores an uploaded file and registers the corresponding document."""

    def __init__(
        self,
        *,
        documents: DocumentService,
        formats: DocumentFormatRepository,
        storage: ObjectStorage,
    ) -> None:
        self._documents = documents
        self._formats = formats
        self._storage = storage

    async def upload(
        self,
        *,
        user_id: UUID,
        subject_id: UUID,
        title: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> Document:
        """Store the file and create the document (owned via its subject).

        The upload is validated (extension + declared MIME + real magic bytes)
        before anything is persisted; an invalid file raises a 415.
        """
        validate_document_upload(
            filename=filename, content_type=content_type, data=data
        )
        suffix = Path(filename).suffix.lower()
        fmt = await self._formats.get_or_create(suffix.lstrip(".") or "bin")
        object_name = f"{subject_id}/{uuid4().hex}{suffix}"
        await run_in_threadpool(
            self._storage.put_object,
            object_name,
            data,
            content_type or "application/octet-stream",
        )
        return await self._documents.register(
            user_id=user_id,
            subject_id=subject_id,
            title=title,
            document_path=object_name,
            document_format_id=fmt.uuid,
        )
