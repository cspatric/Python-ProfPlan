"""Response schemas for documents."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Public representation of a document."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    subject_id: UUID
    document_format_id: UUID | None
    title: str
    document_path: str
    created_at: datetime
    updated_at: datetime
