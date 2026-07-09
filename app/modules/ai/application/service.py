"""AI use cases: answer a question grounded on the user's documents (RAG)."""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.ai.domain.prompts import (
    ASSISTANT_SYSTEM_PROMPT,
    build_rag_prompt,
)
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.domain.chunk import SearchResult
from app.modules.rag.domain.interfaces import Embedder
from app.modules.rag.infrastructure.repository import ChunkRepository

logger = logging.getLogger("app.ai")


@dataclass(slots=True)
class AiAnswer:
    """A generated answer with its provider and the sources it used."""

    answer: str
    provider: str
    sources: list[str]


class AiService:
    """Retrieval-augmented generation over the user's documents.

    Opens its own short-lived DB session for the read-only retrieval phase
    and closes it *before* calling the LLM gateway — the fallback chain can
    take up to several minutes (multiple providers, each retried, each with a
    60s timeout), and holding a pooled connection for that long would let a
    handful of concurrent requests exhaust the whole API pool.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        session_factory: async_sessionmaker,
        embedder: Embedder,
    ) -> None:
        self._gateway = gateway
        self._session_factory = session_factory
        self._embedder = embedder

    async def answer(
        self,
        *,
        user_id: UUID,
        query: str,
        subject_id: UUID | None = None,
        limit: int = 5,
    ) -> AiAnswer:
        """Retrieve relevant chunks, then generate an answer via the gateway.

        Retrieval is best-effort: if the embedding backend is unavailable (e.g.
        Ollama/bge-m3 is down) the question is still answered, just without
        document grounding — a degraded answer beats a 500.
        """
        async with self._session_factory() as session:
            retrieval = RetrievalService(
                self._embedder,
                SearchService(ChunkRepository(session)),
                DocumentContentRepository(session),
            )
            try:
                chunks = await retrieval.query(
                    user_id=user_id, query=query, subject_id=subject_id, limit=limit
                )
            except Exception:  # noqa: BLE001 — RAG context is best-effort
                logger.warning("RAG retrieval unavailable; answering without context")
                chunks: list[SearchResult] = []
            disabled = await AiProviderRepository(session).disabled_names()

        context = "\n\n".join(
            f"[{i + 1}] {chunk.content}" for i, chunk in enumerate(chunks)
        )
        result = await self._gateway.generate(
            build_rag_prompt(query, context),
            system=ASSISTANT_SYSTEM_PROMPT,
            disabled=disabled,
        )
        return AiAnswer(
            answer=result.text,
            provider=result.provider,
            sources=[chunk.chunk_id for chunk in chunks],
        )
