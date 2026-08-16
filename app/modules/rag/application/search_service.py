"""Retrieval use case: similarity search, optionally fused with a word search."""

from collections.abc import Sequence
from uuid import UUID

from app.core.config import get_settings
from app.modules.rag.domain.chunk import SearchResult
from app.modules.rag.infrastructure.repository import ChunkRepository


class SearchService:
    """Finds the chunks most relevant to a query."""

    def __init__(self, chunks: ChunkRepository) -> None:
        self._chunks = chunks

    async def search(
        self,
        *,
        query_embedding: list[float],
        limit: int = 5,
        content_ids: Sequence[UUID],
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Return the ``limit`` most relevant chunks.

        With ``query_text`` and hybrid search on, a word search runs alongside
        the vector one and the two rankings are fused; a vector search alone is
        blind to the tokens that carry no meaning to average, a surname, an
        acronym, a year, which are often the exact words a teacher searched for.

        Ownership scoping is mandatory: ``content_ids`` are the ids of the
        contents the user is allowed to read. An empty scope returns nothing —
        the search is never run unscoped (tenant isolation).
        """
        if not content_ids:
            return []

        settings = get_settings()
        if query_text and settings.rag_hybrid_search:
            fused = await self._chunks.search_hybrid(
                query_embedding,
                query_text,
                limit=limit,
                content_ids=content_ids,
                pool=settings.rag_candidate_pool,
                rrf_k=settings.rag_rrf_k,
            )
            return [
                SearchResult(
                    chunk_id=str(chunk.uuid),
                    document_content_id=str(chunk.document_content_id),
                    content=chunk.content,
                    distance=float(distance),
                    vector_rank=vector_rank,
                    lexical_rank=lexical_rank,
                )
                for chunk, distance, vector_rank, lexical_rank in fused
            ]

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
