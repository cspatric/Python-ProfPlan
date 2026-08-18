"""Persistence access for documents and their parsed content."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.domain.entities import IngestionStatus
from app.modules.documents.infrastructure.models import (
    Document,
    DocumentContent,
    DocumentFormat,
)
from app.modules.subjects.infrastructure.models import Subject


class DocumentRepository:
    """Data-access layer for the document table (owner scoped via subject)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, document: Document) -> None:
        """Stage a new document for insertion."""
        self._session.add(document)

    async def get_by_id(self, document_id: UUID, user_id: UUID) -> Document | None:
        """Return a non-deleted document owned by the user (via its subject)."""
        stmt = (
            select(Document)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Document.uuid == document_id,
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[Document]:
        """Every non-deleted document the user owns, across all subjects.

        The library screen needs one list, not one request per subject: a
        teacher with thirty subjects would otherwise open thirty connections to
        draw one page. The ownership scope is the same join as everywhere else —
        it is the subject that carries the owner, so the join is what makes this
        safe, not the caller.
        """
        stmt = (
            select(Document)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
                Subject.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_subject(
        self, subject_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[Document]:
        """Return a subject's non-deleted documents, most recent first."""
        stmt = (
            select(Document)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Document.subject_id == subject_id,
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_processing(self, document_id: UUID) -> Document | None:
        """Return a document by id without user scoping (worker use)."""
        result = await self._session.execute(
            select(Document).where(
                Document.uuid == document_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def set_ingestion_status(
        self,
        document_id: UUID,
        status: IngestionStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Update a document's ingestion status (does not commit)."""
        values: dict[str, object] = {
            "ingestion_status": status,
            "ingestion_error": error,
        }
        if status is IngestionStatus.PROCESSING:
            # A fresh run starts the clock over. Keeping the previous run's
            # start would make the estimate read as hours remaining on a
            # document that was just re-queued.
            values |= {
                "ingestion_started_at": datetime.now(UTC),
                "ingestion_chunks_done": 0,
                "ingestion_chunks_total": None,
            }
        await self._session.execute(
            update(Document).where(Document.uuid == document_id).values(**values)
        )

    async def set_ingestion_progress(
        self, document_id: UUID, *, done: int, total: int
    ) -> None:
        """Record how far the embedding has got (does not commit)."""
        await self._session.execute(
            update(Document)
            .where(Document.uuid == document_id)
            .values(ingestion_chunks_done=done, ingestion_chunks_total=total)
        )


class DocumentFormatRepository:
    """Data-access layer for the document_format catalog."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, fmt: str) -> DocumentFormat:
        """Return the format row for ``fmt``, creating it if needed."""
        result = await self._session.execute(
            select(DocumentFormat).where(DocumentFormat.format == fmt)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        document_format = DocumentFormat(format=fmt)
        self._session.add(document_format)
        await self._session.flush()
        return document_format


class DocumentContentRepository:
    """Data-access layer for the document_content table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, content: DocumentContent) -> None:
        """Stage a new parsed content for insertion."""
        self._session.add(content)

    async def get_by_id(self, content_id: UUID) -> DocumentContent | None:
        """Return a parsed content by id."""
        result = await self._session.execute(
            select(DocumentContent).where(DocumentContent.uuid == content_id)
        )
        return result.scalar_one_or_none()

    async def list_by_document(self, document_id: UUID) -> list[DocumentContent]:
        """Return every parsed content of a document, newest version first."""
        stmt = (
            select(DocumentContent)
            .where(DocumentContent.document_id == document_id)
            .order_by(DocumentContent.version.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self, document_id: UUID) -> DocumentContent | None:
        """Return the most recent parsed content of a document."""
        stmt = (
            select(DocumentContent)
            .where(DocumentContent.document_id == document_id)
            .order_by(DocumentContent.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_content_ids_for_user(
        self, user_id: UUID, subject_id: UUID | None = None
    ) -> list[UUID]:
        """Return the content ids the user is allowed to search over.

        Scoped to the user's non-deleted documents, optionally to one subject.
        """
        stmt = (
            select(DocumentContent.uuid)
            .join(Document, DocumentContent.document_id == Document.uuid)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        if subject_id is not None:
            stmt = stmt.where(Document.subject_id == subject_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def has_content(self, document_id: UUID) -> bool:
        """Return True if the document has at least one parsed content."""
        result = await self._session.execute(
            select(DocumentContent.uuid)
            .where(DocumentContent.document_id == document_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
