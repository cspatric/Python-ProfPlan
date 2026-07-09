"""Persistence access for chunks, including vector similarity search."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.infrastructure.models import Chunk


class ChunkRepository:
    """Data-access layer for the chunks table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_many(self, chunks: Sequence[Chunk]) -> None:
        """Stage several chunks for insertion."""
        self._session.add_all(chunks)

    async def list_by_content(self, content_id: UUID) -> list[Chunk]:
        """Return a content's chunks in order."""
        stmt = (
            select(Chunk)
            .where(Chunk.document_content_id == content_id)
            .order_by(Chunk.chunk_index.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_content(self, content_id: UUID) -> None:
        """Delete every chunk of a content (e.g. before re-indexing)."""
        for chunk in await self.list_by_content(content_id):
            await self._session.delete(chunk)

    async def search_similar(
        self,
        embedding: list[float],
        *,
        limit: int,
        content_ids: Sequence[UUID],
    ) -> list[tuple[Chunk, float]]:
        """Return the nearest chunks by cosine distance (smaller is closer).

        Tenant isolation: the search is ALWAYS scoped to ``content_ids`` (the
        contents the caller is allowed to read). An empty scope returns nothing —
        we never run an unscoped similarity search, so one user's query can never
        match another user's chunks.
        """
        if not content_ids:
            return []
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            select(Chunk, distance.label("distance"))
            .where(
                Chunk.embedding.is_not(None),
                Chunk.document_content_id.in_(content_ids),
            )
            .order_by(distance.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
