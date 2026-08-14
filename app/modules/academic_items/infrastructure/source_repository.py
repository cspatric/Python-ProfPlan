"""Reading and writing the passages an item was written from."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItemSource
from app.modules.documents.infrastructure.models import Document, DocumentContent
from app.modules.rag.domain.chunk import SearchResult


class AcademicItemSourceRepository:
    """The citations of a generated item."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace(self, item_id: UUID, results: list[SearchResult]) -> None:
        """Record these passages as the item's sources, dropping any previous.

        Replacing rather than appending: an item that is regenerated was
        written from whatever was retrieved *this* time, and leaving the old
        rows would attribute the new text to passages that had nothing to do
        with it.
        """
        await self._session.execute(
            delete(AcademicItemSource).where(
                AcademicItemSource.academic_item_id == item_id
            )
        )
        if not results:
            return

        # One query for every document behind the retrieved passages, so a
        # citation can name the file instead of a uuid.
        content_ids = [UUID(r.document_content_id) for r in results]
        rows = await self._session.execute(
            select(DocumentContent.uuid, Document.uuid)
            .join(Document, Document.uuid == DocumentContent.document_id)
            .where(DocumentContent.uuid.in_(content_ids))
        )
        document_of = dict(rows.all())

        for rank, result in enumerate(results, start=1):
            self._session.add(
                AcademicItemSource(
                    academic_item_id=item_id,
                    chunk_id=UUID(result.chunk_id),
                    document_id=document_of.get(UUID(result.document_content_id)),
                    rank=rank,
                    distance=result.distance,
                    section=result.section,
                    excerpt=result.content,
                )
            )

    async def list_for_item(
        self, item_id: UUID
    ) -> list[tuple[AcademicItemSource, str | None]]:
        """Return (source, document title) in the order the prompt used."""
        rows = await self._session.execute(
            select(AcademicItemSource, Document.title)
            .outerjoin(Document, Document.uuid == AcademicItemSource.document_id)
            .where(AcademicItemSource.academic_item_id == item_id)
            .order_by(AcademicItemSource.rank)
        )
        return [(source, title) for source, title in rows.all()]
