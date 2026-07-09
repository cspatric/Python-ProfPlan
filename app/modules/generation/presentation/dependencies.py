"""FastAPI dependencies for the generation module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.ai.infrastructure.gateway.llm_gateway import get_gateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.generation.application.service import GenerationService
from app.modules.generation.infrastructure.plan_document_repository import (
    PlanDocumentRepository,
)
from app.modules.generation.infrastructure.repository import GenerationRepository
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.infrastructure.embedding.cache import build_cached_embedder
from app.modules.rag.infrastructure.repository import ChunkRepository
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.teaching_plans.infrastructure.repository import PlanRepository


def get_generation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GenerationService:
    """Build a GenerationService (planner + RAG retrieval + LLM gateway)."""
    retrieval = RetrievalService(
        build_cached_embedder(),
        SearchService(ChunkRepository(session)),
        DocumentContentRepository(session),
    )
    return GenerationService(
        session,
        gateway=get_gateway(),
        retrieval=retrieval,
        plans=PlanRepository(session),
        repo=GenerationRepository(session),
        providers=AiProviderRepository(session),
        subjects=SubjectRepository(session),
        plan_docs=PlanDocumentRepository(session),
    )


GenerationServiceDep = Annotated[GenerationService, Depends(get_generation_service)]
