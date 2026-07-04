"""Retrieval use case: cosine similarity search over chunk embeddings."""

from collections.abc import Sequence
from uuid import UUID

from app.modules.rag.domain.chunk import SearchResult
from app.modules.rag.infrastructure.repository import ChunkRepository


class SearchService:
    """Finds the chunks most similar to a query embedding."""

    def __init__(self, chunks: ChunkRepository) -> None:
        self._chunks = chunks

    async def search(
        self,
        *,
        query_embedding: list[float],
        limit: int = 5,
        content_ids: Sequence[UUID] | None = None,
    ) -> list[SearchResult]:
        """Return the ``limit`` closest chunks by cosine distance.

        Ownership scoping is the caller's responsibility: pass the ids of the
        contents the user is allowed to read via ``content_ids``.
        """
        rows = await self._chunks.search_similar(
            query_embedding, limit=limit, content_ids=content_ids
        )
        return [
            SearchResult(
                chunk_id=str(chunk.uuid),
                document_content_id=str(chunk.document_content_id),
                content=chunk.content,
                distance=float(distance),
            )
            for chunk, distance in rows
        ]
