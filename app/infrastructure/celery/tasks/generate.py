"""Celery task: generate one academic item of a plan-generation run.

One task per item (fan-out). Uses the NullPool worker engine (loop-safe) and
the same retry/backoff pattern as document ingestion. LLM outages are transient,
so every failure is retried; after exhausting retries the item is marked FAILED
and the run recomputed to PARTIAL.
"""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.celery.worker import celery_app
from app.infrastructure.database.session import WorkerSessionFactory
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

_MAX_RETRIES = 3


def _build_service(session: AsyncSession) -> GenerationService:
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


async def _run(item_id: UUID) -> None:
    async with WorkerSessionFactory() as session:
        await _build_service(session).process_item(item_id)


async def _fail(item_id: UUID, error: str) -> None:
    async with WorkerSessionFactory() as session:
        await _build_service(session).mark_item_failed(item_id, error)


@celery_app.task(bind=True, name="generation.run_item", max_retries=_MAX_RETRIES)
def run_item(self, item_id: str) -> None:
    """Generate one academic item; retry transient failures, then FAILED."""
    item_uuid = UUID(item_id)
    try:
        asyncio.run(_run(item_uuid))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            asyncio.run(_fail(item_uuid, str(exc)))
            raise
        # Exponential backoff: 15s, 30s, 60s.
        raise self.retry(exc=exc, countdown=15 * 2**self.request.retries) from exc
