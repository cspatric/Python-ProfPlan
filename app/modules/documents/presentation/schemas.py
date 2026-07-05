"""Response schemas for documents."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.documents.domain.entities import IngestionStatus


class DocumentResponse(BaseModel):
    """Public representation of a document."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    subject_id: UUID
    document_format_id: UUID | None
    title: str
    document_path: str
    ingestion_status: IngestionStatus
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    """Ingestion status of a document."""

    document_id: UUID
    status: IngestionStatus
    error: str | None = None
