"""Document use cases (register, list, soft-delete, parsed content)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.domain.exceptions import (
    DocumentNotFoundError,
    InvalidSubjectError,
)
from app.modules.documents.infrastructure.models import (
    Document,
    DocumentContent,
)
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.subjects.infrastructure.repository import SubjectRepository


class DocumentService:
    """Coordinates document operations, scoped to the owner via its subject."""

    def __init__(
        self,
        session: AsyncSession,
        documents: DocumentRepository,
        subjects: SubjectRepository,
    ) -> None:
        self._session = session
        self._documents = documents
        self._subjects = subjects

    async def _ensure_subject_owned(self, subject_id: UUID, user_id: UUID) -> None:
        if await self._subjects.get_by_id(subject_id, user_id) is None:
            raise InvalidSubjectError

    async def register(
        self,
        *,
        user_id: UUID,
        subject_id: UUID,
        title: str,
        document_path: str,
        document_format_id: UUID | None = None,
    ) -> Document:
        """Register an uploaded document for a subject owned by the user."""
        await self._ensure_subject_owned(subject_id, user_id)
        document = Document(
            subject_id=subject_id,
            title=title,
            document_path=document_path,
            document_format_id=document_format_id,
        )
        self._documents.add(document)
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def get(self, *, user_id: UUID, document_id: UUID) -> Document:
        """Return a single document or raise if not found."""
        document = await self._documents.get_by_id(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError
        return document

    async def list_by_subject(
        self, *, user_id: UUID, subject_id: UUID, limit: int, offset: int
    ) -> list[Document]:
        """List a subject's documents."""
        await self._ensure_subject_owned(subject_id, user_id)
        return await self._documents.list_by_subject(
            subject_id, user_id, limit=limit, offset=offset
        )

    async def soft_delete(self, *, user_id: UUID, document_id: UUID) -> None:
        """Soft-delete a document (sets deleted_at)."""
        document = await self.get(user_id=user_id, document_id=document_id)
        document.deleted_at = datetime.now(UTC)
        await self._session.commit()


class DocumentContentService:
    """Manages the parsed (markdown) content versions of a document."""

    def __init__(
        self,
        session: AsyncSession,
        contents: DocumentContentRepository,
        documents: DocumentRepository,
    ) -> None:
        self._session = session
        self._contents = contents
        self._documents = documents

    async def _ensure_document_owned(self, document_id: UUID, user_id: UUID) -> None:
        if await self._documents.get_by_id(document_id, user_id) is None:
            raise DocumentNotFoundError

    async def add_content(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        markdown: str,
        language: str | None = None,
        parser: str | None = None,
    ) -> DocumentContent:
        """Store a new parsed content, auto-incrementing the version."""
        await self._ensure_document_owned(document_id, user_id)
        latest = await self._contents.get_latest(document_id)
        version = latest.version + 1 if latest else 1
        content = DocumentContent(
            document_id=document_id,
            markdown=markdown,
            language=language,
            parser=parser,
            version=version,
        )
        self._contents.add(content)
        await self._session.commit()
        await self._session.refresh(content)
        return content

    async def get_latest(
        self, *, user_id: UUID, document_id: UUID
    ) -> DocumentContent | None:
        """Return the most recent parsed content of a document."""
        await self._ensure_document_owned(document_id, user_id)
        return await self._contents.get_latest(document_id)

    async def list_versions(
        self, *, user_id: UUID, document_id: UUID
    ) -> list[DocumentContent]:
        """Return every parsed content version of a document."""
        await self._ensure_document_owned(document_id, user_id)
        return await self._contents.list_by_document(document_id)
