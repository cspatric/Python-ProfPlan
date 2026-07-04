"""FastAPI dependencies for the documents module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.storage.minio import get_object_storage
from app.modules.documents.application.document_service import DocumentService
from app.modules.documents.application.upload_service import UploadService
from app.modules.documents.infrastructure.repository import (
    DocumentFormatRepository,
    DocumentRepository,
)
from app.modules.subjects.infrastructure.repository import SubjectRepository


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentService:
    """Build a DocumentService wired to the request-scoped session."""
    return DocumentService(
        session, DocumentRepository(session), SubjectRepository(session)
    )


def get_upload_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadService:
    """Build an UploadService wired to the request-scoped session."""
    return UploadService(
        documents=get_document_service(session),
        formats=DocumentFormatRepository(session),
        storage=get_object_storage(),
    )


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
UploadServiceDep = Annotated[UploadService, Depends(get_upload_service)]
