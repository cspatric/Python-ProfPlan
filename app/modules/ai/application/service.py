"""AI use cases: answer a question grounded on the user's documents (RAG)."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.ai.domain.prompts import (
    ASSISTANT_SYSTEM_PROMPT,
    build_rag_prompt,
)
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.rag.application.retrieval_service import RetrievalService


@dataclass(slots=True)
class AiAnswer:
    """A generated answer with its provider and the sources it used."""

    answer: str
    provider: str
    sources: list[str]


class AiService:
    """Retrieval-augmented generation over the user's documents."""

    def __init__(
        self,
        gateway: LLMGateway,
        retrieval: RetrievalService,
        providers: AiProviderRepository,
    ) -> None:
        self._gateway = gateway
        self._retrieval = retrieval
        self._providers = providers

    async def answer(
        self,
        *,
        user_id: UUID,
        query: str,
        subject_id: UUID | None = None,
        limit: int = 5,
    ) -> AiAnswer:
        """Retrieve relevant chunks, then generate an answer via the gateway."""
        chunks = await self._retrieval.query(
            user_id=user_id, query=query, subject_id=subject_id, limit=limit
        )
        context = "\n\n".join(
            f"[{i + 1}] {chunk.content}" for i, chunk in enumerate(chunks)
        )
        disabled = await self._providers.disabled_names()
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
