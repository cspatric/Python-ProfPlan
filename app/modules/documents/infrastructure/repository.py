"""Persistence access for documents and their parsed content."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.infrastructure.models import (
    Document,
    DocumentContent,
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
