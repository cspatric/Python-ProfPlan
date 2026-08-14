"""Response schemas for documents."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.documents.domain.entities import IngestionStatus

#: Matches the ``documents.title`` column, so a title that validates also fits.
MAX_DOCUMENT_TITLE = 255


class DocumentResponse(BaseModel):
    """Public representation of a document."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    subject_id: UUID
    document_format_id: UUID | None
    title: str
    document_path: str
    ingestion_status: IngestionStatus
    # How far the embedding has got, and since when, so the page can say "42 of
    # 154, about six minutes left" instead of spinning indefinitely on a job
    # that runs for minutes. Null until the text has been chunked, which is the
    # first moment the size of the job is known.
    #
    # Flat, and named exactly like the columns, on purpose: `model_validate`
    # then fills them from the row with nothing to wire by hand. A nested
    # object would need a builder, and a builder is what silently dropped
    # `generation_status` from the academic item response for a whole release.
    #
    # The estimate itself is not computed here. It belongs where the clock is
    # already ticking; a number computed server-side is stale the moment it is
    # serialised.
    ingestion_chunks_total: int | None = None
    ingestion_chunks_done: int | None = None
    ingestion_started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    """Ingestion status of a document."""

    document_id: UUID
    status: IngestionStatus
    error: str | None = None
