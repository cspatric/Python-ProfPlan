"""Document HTTP endpoints (upload triggers async ingestion)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.infrastructure.celery.tasks.ingest import ingest_document
from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.documents.presentation.dependencies import (
    ContentServiceDep,
    DocumentServiceDep,
    UploadServiceDep,
)
from app.modules.documents.presentation.schemas import (
    DocumentResponse,
    DocumentStatusResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    user: CurrentUser,
    service: UploadServiceDep,
    subject_id: Annotated[UUID, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    """Upload a document; it is stored and queued for async ingestion."""
    data = await file.read()
    document = await service.upload(
        user_id=user.uuid,
        subject_id=subject_id,
        title=title,
        filename=file.filename or "document",
        data=data,
        content_type=file.content_type or "application/octet-stream",
    )
    ingest_document.delay(str(document.uuid))
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    subject_id: UUID,
    user: CurrentUser,
    service: DocumentServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentResponse]:
    """List the documents of a subject owned by the user."""
    documents = await service.list_by_subject(
        user_id=user.uuid, subject_id=subject_id, limit=limit, offset=offset
    )
    return [DocumentResponse.model_validate(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID, user: CurrentUser, service: DocumentServiceDep
) -> DocumentResponse:
    """Return a single document."""
    document = await service.get(user_id=user.uuid, document_id=document_id)
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID, user: CurrentUser, service: ContentServiceDep
) -> DocumentStatusResponse:
    """Return whether the document has finished ingestion."""
    state = await service.get_status(user_id=user.uuid, document_id=document_id)
    return DocumentStatusResponse(document_id=document_id, status=state)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, user: CurrentUser, service: DocumentServiceDep
) -> None:
    """Soft-delete a document."""
    await service.soft_delete(user_id=user.uuid, document_id=document_id)
