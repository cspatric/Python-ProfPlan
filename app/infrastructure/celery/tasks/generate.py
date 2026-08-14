"""Celery task: generate one academic item of a plan-generation run.

One task per item (fan-out). Uses the NullPool worker engine (loop-safe) and
the same retry/backoff pattern as document ingestion. LLM outages are transient,
so every failure is retried; after exhausting retries the item is marked FAILED
and the run recomputed to PARTIAL.
"""

import asyncio
import time
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.celery import dead_letter
from app.infrastructure.celery.worker import celery_app
from app.infrastructure.database.session import WorkerSessionFactory
from app.infrastructure.redis.client import new_redis_client
from app.infrastructure.telemetry.metrics import PLAN_DRAFT_SECONDS, PLAN_DRAFTS
from app.modules.academic_items.infrastructure.source_repository import (
    AcademicItemSourceRepository,
)
from app.modules.ai.infrastructure.gateway.llm_gateway import build_gateway
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


def _build_service(session: AsyncSession, redis: Redis) -> GenerationService:
    # Redis-backed pieces (breakers, embed cache) take the per-run client:
    # this whole graph lives and dies inside one asyncio.run(), and pooled
    # connections must never outlive the loop that created them.
    retrieval = RetrievalService(
        build_cached_embedder(redis),
        SearchService(ChunkRepository(session)),
        DocumentContentRepository(session),
    )
    return GenerationService(
        session,
        gateway=build_gateway(redis),
        retrieval=retrieval,
        plans=PlanRepository(session),
        repo=GenerationRepository(session),
        providers=AiProviderRepository(session),
        subjects=SubjectRepository(session),
        plan_docs=PlanDocumentRepository(session),
        sources=AcademicItemSourceRepository(session),
    )


async def _run(item_id: UUID) -> None:
    redis = new_redis_client()
    try:
        async with WorkerSessionFactory() as session:
            await _build_service(session, redis).process_item(item_id)
    finally:
        await redis.aclose()


async def _fail(item_id: UUID, error: str) -> None:
    redis = new_redis_client()
    try:
        async with WorkerSessionFactory() as session:
            await _build_service(session, redis).mark_item_failed(item_id, error)
    finally:
        await redis.aclose()


@celery_app.task(bind=True, name="generation.run_item", max_retries=_MAX_RETRIES)
def run_item(self, item_id: str) -> None:
    """Generate one academic item; retry transient failures, then FAILED."""
    item_uuid = UUID(item_id)
    try:
        asyncio.run(_run(item_uuid))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            asyncio.run(_fail(item_uuid, str(exc)))
            dead_letter.record(
                task=self.name,
                args=(item_id,),
                error=str(exc),
                retries=self.request.retries,
            )
            raise
        # Exponential backoff: 15s, 30s, 60s.
        raise self.retry(exc=exc, countdown=15 * 2**self.request.retries) from exc


async def _plan(plan_id: UUID, user_id: UUID, run_id: UUID, teacher_input: str | None):
    redis = new_redis_client()
    try:
        async with WorkerSessionFactory() as session:
            service = _build_service(session, redis)
            return await service.plan_existing_run(
                user_id=user_id,
                plan_id=plan_id,
                run_id=run_id,
                teacher_input=teacher_input,
            )
    finally:
        await redis.aclose()


async def _fail_run(run_id: UUID, error: str) -> None:
    redis = new_redis_client()
    try:
        async with WorkerSessionFactory() as session:
            await _build_service(session, redis).fail_run(run_id, error)
    finally:
        await redis.aclose()


@celery_app.task(bind=True, name="plans.generate", max_retries=_MAX_RETRIES)
def generate_plan(
    self,
    plan_id: str,
    user_id: str,
    run_id: str,
    teacher_input: str | None = None,
    queued_at: float | None = None,
) -> None:
    """Draft the roadmap for a plan, then fan out one task per item.

    This is the call that used to happen inside the HTTP request. It takes up
    to a minute, and a browser that lost the connection meanwhile left the
    teacher with no plan on screen and a plan in the database.
    """
    run_uuid = UUID(run_id)
    try:
        items = asyncio.run(
            _plan(UUID(plan_id), UUID(user_id), run_uuid, teacher_input)
        )
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # The run carries the reason, which is what the page reads: a plan
            # whose roadmap never arrived has to say so rather than spin.
            asyncio.run(_fail_run(run_uuid, str(exc)))
            PLAN_DRAFTS.labels(outcome="failed").inc()
            dead_letter.record(
                task=self.name,
                args=(plan_id, user_id, run_id, teacher_input),
                error=str(exc),
                retries=self.request.retries,
            )
            raise
        raise self.retry(exc=exc, countdown=15 * 2**self.request.retries) from exc

    # Timed from when the request queued this, not from when the worker picked
    # it up: the teacher is waiting through the queue too, and under load the
    # queue is where the wait actually grows.
    if queued_at is not None:
        PLAN_DRAFT_SECONDS.observe(max(time.time() - queued_at, 0.0))
    PLAN_DRAFTS.labels(outcome="drafted").inc()

    for item_id in items:
        run_item.delay(str(item_id))
