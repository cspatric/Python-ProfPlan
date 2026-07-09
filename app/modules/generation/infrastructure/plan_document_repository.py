"""Persistence for the plan<->document selection (RAG scoping)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.infrastructure.models import Document, DocumentContent
from app.modules.generation.infrastructure.models import PlanDocument
from app.modules.subjects.infrastructure.models import Subject


class PlanDocumentRepository:
    """Links documents to a plan and resolves the plan's RAG content ids."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def link(self, plan_id: UUID, document_id: UUID) -> None:
        """Stage a plan<->document link (caller commits)."""
        self._session.add(PlanDocument(plan_id=plan_id, document_id=document_id))

    async def owned_document_ids(
        self, document_ids: Sequence[UUID], user_id: UUID
    ) -> set[UUID]:
        """Return which of ``document_ids`` are non-deleted docs owned by user."""
        if not document_ids:
            return set()
        stmt = (
            select(Document.uuid)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Document.uuid.in_(document_ids),
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def content_ids_for_documents(
        self, document_ids: Sequence[UUID], user_id: UUID
    ) -> list[UUID]:
        """Content ids of the given documents (scoped to the user)."""
        if not document_ids:
            return []
        stmt = (
            select(DocumentContent.uuid)
            .join(Document, DocumentContent.document_id == Document.uuid)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                Document.uuid.in_(document_ids),
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def content_ids_for_plan(self, plan_id: UUID, user_id: UUID) -> list[UUID]:
        """Content ids of the documents linked to a plan (scoped to the user)."""
        stmt = (
            select(DocumentContent.uuid)
            .join(Document, DocumentContent.document_id == Document.uuid)
            .join(PlanDocument, PlanDocument.document_id == Document.uuid)
            .join(Subject, Document.subject_id == Subject.uuid)
            .where(
                PlanDocument.plan_id == plan_id,
                Subject.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
