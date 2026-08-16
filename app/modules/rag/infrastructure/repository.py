"""Persistence access for chunks, including vector similarity search."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import text as text_clause
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

    async def _or_terms(self, text: str) -> str | None:
        """Turn a question into a tsquery of its words joined by OR.

        This is the difference between a lexical *search* and a lexical
        *filter*. `websearch_to_tsquery` joins terms with AND, so "why are food
        chains short" only matches a passage containing every one of those
        words, and a natural question matches nothing at all. Ranking, not
        matching, is what separates the good hits from the rest: OR finds every
        passage sharing any term and `ts_rank_cd` puts the ones sharing several,
        close together, on top. That is the behaviour people mean by BM25.

        Postgres does the tokenising, with the same configuration the index
        uses, so stopwords disappear and stemming agrees on both sides. A
        question of nothing but stopwords returns None: there is no lexical
        search to run.
        """
        terms = await self._session.scalar(
            text_clause(
                "SELECT string_agg(lexeme, ' | ') "
                "FROM unnest(to_tsvector('english', :query_text))"
            ),
            {"query_text": text},
        )
        return terms or None

    async def search_lexical(
        self,
        text: str,
        *,
        limit: int,
        content_ids: Sequence[UUID],
    ) -> list[tuple[Chunk, float]]:
        """Rank chunks by word overlap alone, ignoring the embedding.

        Not used in production, where the fused search is what runs. It exists
        so the evaluation can score this half on its own: measuring it by
        filtering the fused list would score it after fusion had already thrown
        most of it away, which is how a perfectly good arm looks useless.

        `ts_rank_cd` rather than `ts_rank`: it takes proximity into account, so
        a chunk where the query's words appear together beats one where they
        happen to appear in different paragraphs.
        """
        terms = await self._or_terms(text)
        if not content_ids or terms is None:
            return []
        sql = text_clause(
            """
            WITH q AS (SELECT (:query_terms)::tsquery AS query)
            SELECT c.uuid, ts_rank_cd(c.content_tsv, q.query) AS score
            FROM chunks c, q
            WHERE c.document_content_id = ANY(:content_ids)
              AND c.content_tsv @@ q.query
            ORDER BY score DESC
            LIMIT :limit
            """
        )
        rows = (
            await self._session.execute(
                sql,
                {
                    "query_terms": terms,
                    "content_ids": list(content_ids),
                    "limit": limit,
                },
            )
        ).all()
        found = {
            chunk.uuid: chunk
            for chunk in (
                await self._session.scalars(
                    select(Chunk).where(Chunk.uuid.in_([row.uuid for row in rows]))
                )
            ).all()
        }
        return [
            (found[row.uuid], float(row.score)) for row in rows if row.uuid in found
        ]

    async def search_hybrid(
        self,
        embedding: list[float],
        text: str,
        *,
        limit: int,
        content_ids: Sequence[UUID],
        pool: int,
        rrf_k: int,
    ) -> list[tuple[Chunk, float, int | None, int | None]]:
        """Fuse a vector search and a word search into one ranking.

        Returns (chunk, cosine distance, vector rank, lexical rank), the two
        ranks being 1-based positions in each list and None when that list did
        not find the chunk at all.

        **Reciprocal rank fusion**, not a weighted sum of scores. Cosine
        distance and ts_rank_cd are different quantities on different scales
        with no meaningful conversion between them; any weighting of the two is
        a magic number that happens to work on the documents it was tuned on.
        RRF only reads the *positions*, which is the one thing the two lists
        genuinely agree on, and is why it survives a change of embedding model
        or corpus without retuning. `rrf_k` flattens the curve so that rank 1
        does not swamp everything: at k=60 the first result is worth 1/61 and
        the tenth 1/70, close enough that agreement between the two lists beats
        a strong showing in one.

        A chunk found by both lists therefore outranks a chunk that only one
        list loved, which is the whole reason to run two searches.

        Ownership scoping is mandatory and applied inside both halves: an
        unscoped lexical search would be a way to read another account's
        documents by guessing a word.
        """
        terms = await self._or_terms(text)
        if not content_ids or terms is None:
            # No searchable word left after stopwords, so there is no lexical
            # half to fuse with. Falling back to the vector search alone is the
            # honest answer, not an empty result.
            rows = await self.search_similar(
                embedding, limit=limit, content_ids=content_ids
            )
            return [
                (chunk, float(distance), rank, None)
                for rank, (chunk, distance) in enumerate(rows, start=1)
            ]

        # The pool is deliberately larger than the limit: fusion can only
        # promote a chunk that at least one of the lists returned, so cutting
        # both lists at `limit` would throw away exactly the agreements this
        # exists to find.
        sql = text_clause(
            """
            WITH semantic AS (
                SELECT uuid,
                       embedding <=> CAST(:embedding AS vector) AS distance,
                       ROW_NUMBER() OVER (
                           ORDER BY embedding <=> CAST(:embedding AS vector)
                       ) AS rank
                FROM chunks
                WHERE document_content_id = ANY(:content_ids)
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :pool
            ),
            terms AS (SELECT (:query_terms)::tsquery AS query),
            lexical AS (
                SELECT c.uuid,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(c.content_tsv, t.query) DESC
                       ) AS rank
                FROM chunks c, terms t
                WHERE c.document_content_id = ANY(:content_ids)
                  AND c.content_tsv @@ t.query
                ORDER BY ts_rank_cd(c.content_tsv, t.query) DESC
                LIMIT :pool
            ),
            fused AS (
                SELECT COALESCE(s.uuid, l.uuid) AS uuid,
                       s.distance,
                       s.rank AS vector_rank,
                       l.rank AS lexical_rank,
                       COALESCE(1.0 / (:rrf_k + s.rank), 0)
                         + COALESCE(1.0 / (:rrf_k + l.rank), 0) AS score
                FROM semantic s
                FULL OUTER JOIN lexical l ON l.uuid = s.uuid
            )
            SELECT c.uuid,
                   -- A chunk only the word search found still gets a real
                   -- distance, so a citation can say how close it was rather
                   -- than showing a blank where the number should be.
                   COALESCE(f.distance, c.embedding <=> CAST(:embedding AS vector))
                       AS distance,
                   f.vector_rank,
                   f.lexical_rank,
                   f.score
            FROM fused f
            JOIN chunks c ON c.uuid = f.uuid
            ORDER BY f.score DESC, distance ASC
            LIMIT :limit
            """
        )
        rows = (
            await self._session.execute(
                sql,
                {
                    "embedding": str(embedding),
                    "query_terms": terms,
                    "content_ids": list(content_ids),
                    "pool": pool,
                    "limit": limit,
                    "rrf_k": rrf_k,
                },
            )
        ).all()

        found = {
            chunk.uuid: chunk
            for chunk in (
                await self._session.scalars(
                    select(Chunk).where(Chunk.uuid.in_([row.uuid for row in rows]))
                )
            ).all()
        }
        return [
            (found[row.uuid], float(row.distance), row.vector_rank, row.lexical_rank)
            for row in rows
            if row.uuid in found
        ]
