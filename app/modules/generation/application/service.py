"""Plan-generation use cases: plan (sync) -> fan-out (async) -> poll."""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.documents.domain.exceptions import DocumentNotFoundError
from app.modules.generation.application.planner import PlannerAgent
from app.modules.generation.domain.entities import (
    GenerationItemStatus,
    GenerationRunStatus,
)
from app.modules.generation.domain.exceptions import GenerationNotFoundError
from app.modules.generation.domain.prompts import (
    GENERATOR_SYSTEM,
    build_item_prompt,
)
from app.modules.generation.domain.roadmap import Roadmap
from app.modules.generation.infrastructure.models import PlanGeneration
from app.modules.generation.infrastructure.plan_document_repository import (
    PlanDocumentRepository,
)
from app.modules.generation.infrastructure.repository import GenerationRepository
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.teaching_plans.domain.exceptions import (
    InvalidSubjectError,
    PlanNotFoundError,
)
from app.modules.teaching_plans.infrastructure.models import Plan
from app.modules.teaching_plans.infrastructure.repository import PlanRepository


def _plan_info(plan: Plan) -> str:
    return (
        f"Period: {plan.starts_at} to {plan.ends_at}. "
        f"{plan.class_per_week} classes/week, {plan.class_duration} min each."
    )


def _split_period(start: date, end: date, n: int) -> list[tuple[date, date]]:
    """Split [start, end] into n contiguous date ranges (for the modules)."""
    if n <= 0:
        return []
    total = max((end - start).days, 0)
    step = max(1, (total + 1) // n)
    ranges: list[tuple[date, date]] = []
    cursor = start
    for i in range(n):
        seg_start = min(cursor, end)
        seg_end = end if i == n - 1 else min(end, cursor + timedelta(days=step - 1))
        if seg_end < seg_start:
            seg_end = seg_start
        ranges.append((seg_start, seg_end))
        cursor = min(end, seg_end + timedelta(days=1))
    return ranges


async def _retrieve_context(
    retrieval: RetrievalService,
    *,
    user_id: UUID,
    subject_id: UUID | None,
    content_ids: list[UUID] | None,
    query: str,
    limit: int,
) -> str:
    try:
        chunks = await retrieval.query(
            user_id=user_id,
            query=query,
            subject_id=subject_id,
            content_ids=content_ids,
            limit=limit,
        )
    except Exception:  # noqa: BLE001 — context is best-effort
        return ""
    return "\n\n".join(f"[{i + 1}] {c.content}" for i, c in enumerate(chunks))


class GenerationService:
    """Orchestrates a plan generation (planner + per-item fan-out)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        gateway: LLMGateway,
        retrieval: RetrievalService,
        plans: PlanRepository,
        repo: GenerationRepository,
        providers: AiProviderRepository,
        subjects: SubjectRepository,
        plan_docs: PlanDocumentRepository,
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._retrieval = retrieval
        self._plans = plans
        self._repo = repo
        self._providers = providers
        self._subjects = subjects
        self._plan_docs = plan_docs

    @staticmethod
    def default_input() -> str:
        """The AI request used when the teacher does not provide one."""
        return (
            "Create a complete teaching plan for this subject: weekly content "
            "items, practical activities and at least one assessment."
        )

    async def _subject_name(self, subject_id: UUID, user_id: UUID) -> str:
        """Return the owned subject's name (validates ownership, 422 if not)."""
        subject = await self._subjects.get_by_id(subject_id, user_id)
        if subject is None:
            raise InvalidSubjectError
        return subject.name

    async def resolve_documents(
        self, *, user_id: UUID, document_ids: list[UUID]
    ) -> list[UUID]:
        """Validate the selected documents belong to the user; return content ids.

        Raises DocumentNotFoundError (404) if any selected document is unknown or
        not owned by the user.
        """
        if not document_ids:
            return []
        owned = await self._plan_docs.owned_document_ids(document_ids, user_id)
        if set(document_ids) - owned:
            raise DocumentNotFoundError
        return await self._plan_docs.content_ids_for_documents(document_ids, user_id)

    def link_documents(self, plan_id: UUID, document_ids: list[UUID]) -> None:
        """Stage the plan<->document links (caller commits)."""
        for document_id in document_ids:
            self._plan_docs.link(plan_id, document_id)

    async def link_documents_and_commit(
        self, plan_id: UUID, document_ids: list[UUID]
    ) -> None:
        """Link documents to a plan and commit (no-generation path)."""
        self.link_documents(plan_id, document_ids)
        await self._session.commit()

    async def plan_roadmap(
        self,
        *,
        user_id: UUID,
        subject_id: UUID,
        plan_info: str,
        teacher_input: str | None = None,
        content_ids: list[UUID] | None = None,
    ) -> Roadmap:
        """Run the planner agent (the synchronous AI call) and validate it.

        Validates subject ownership first (no AI tokens burned for an invalid
        subject) and anchors the planner on the subject's name. ``content_ids``
        scopes the RAG context to the documents selected for the plan. Raises
        PlannerError (502) / AllProvidersFailedError (503) on failure — callers
        run this BEFORE persisting anything, so an AI failure surfaces as a
        real error and leaves no orphan rows behind.
        """
        subject_name = await self._subject_name(subject_id, user_id)
        disabled = await self._providers.disabled_names()
        planner = PlannerAgent(self._gateway, self._retrieval)
        return await planner.plan(
            user_id=user_id,
            subject_id=subject_id,
            teacher_input=teacher_input or self.default_input(),
            plan_info=f"Subject: {subject_name}. {plan_info}",
            content_ids=content_ids,
            disabled=disabled,
        )

    async def start(
        self, *, user_id: UUID, plan_id: UUID, teacher_input: str | None = None
    ) -> tuple[PlanGeneration, list[AcademicItem]]:
        """Plan + materialise for an existing plan (manual retrigger)."""
        plan = await self._plans.get_by_id(plan_id, user_id)
        if plan is None:
            raise PlanNotFoundError
        content_ids = (
            await self._plan_docs.content_ids_for_plan(plan_id, user_id) or None
        )
        roadmap = await self.plan_roadmap(
            user_id=user_id,
            subject_id=plan.subject_id,
            plan_info=_plan_info(plan),
            teacher_input=teacher_input,
            content_ids=content_ids,
        )
        return await self.materialize(
            user_id=user_id,
            plan=plan,
            roadmap=roadmap,
            teacher_input=teacher_input or self.default_input(),
        )

    async def materialize(
        self,
        *,
        user_id: UUID,
        plan: Plan,
        roadmap: Roadmap,
        teacher_input: str,
    ) -> tuple[PlanGeneration, list[AcademicItem]]:
        """Persist a validated roadmap: run + modules + pending items.

        The caller enqueues one worker task per returned item.
        """
        run = PlanGeneration(
            plan_id=plan.uuid,
            user_id=user_id,
            status=GenerationRunStatus.RUNNING,
            input={"request": teacher_input},
            roadmap=roadmap.model_dump(),
        )
        self._repo.add(run)
        await self._session.flush()

        items: list[AcademicItem] = []
        ranges = _split_period(plan.starts_at, plan.ends_at, len(roadmap.modules))
        for (m_start, m_end), planned_module in zip(
            ranges, roadmap.modules, strict=True
        ):
            module = Module(
                plan_id=plan.uuid,
                user_id=user_id,
                created_by=user_id,
                title=planned_module.title,
                description=planned_module.description,
                start_at=m_start,
                ends_at=m_end,
            )
            self._session.add(module)
            await self._session.flush()
            for planned_item in planned_module.items:
                item = AcademicItem(
                    user_id=user_id,
                    module_id=module.uuid,
                    created_by=user_id,
                    title=planned_item.title,
                    content=None,
                    generation_id=run.uuid,
                    generation_status=GenerationItemStatus.PENDING,
                    generation_prompt=planned_item.prompt,
                    item_metadata={
                        "kind": planned_item.kind,
                        "when": planned_item.when,
                    },
                )
                self._session.add(item)
                items.append(item)

        await self._session.commit()
        await self._session.refresh(run)
        for item in items:
            await self._session.refresh(item)
        return run, items

    async def get(
        self, *, user_id: UUID, generation_id: UUID
    ) -> tuple[PlanGeneration, list[AcademicItem]]:
        """Return a run and its items (for polling)."""
        run = await self._repo.get_by_id(generation_id, user_id)
        if run is None:
            raise GenerationNotFoundError
        items = await self._repo.list_items(generation_id)
        return run, items

    # --- worker side --------------------------------------------------------
    async def process_item(self, item_id: UUID) -> None:
        """Generate one academic item's content (called by the worker)."""
        item = await self._repo.item_for_processing(item_id)
        if item is None or item.generation_id is None:
            return

        item.generation_status = GenerationItemStatus.PROCESSING
        item.generation_error = None
        await self._session.commit()

        run = await self._repo.get_for_processing(item.generation_id)
        plan = await self._plans.get_for_processing(run.plan_id) if run else None
        subject_id = plan.subject_id if plan else None
        plan_info = ""
        content_ids: list[UUID] | None = None
        if plan is not None:
            subject = await self._subjects.get_by_id(plan.subject_id, item.user_id)
            subject_name = f"Subject: {subject.name}. " if subject else ""
            plan_info = f"{subject_name}{_plan_info(plan)}"
            content_ids = (
                await self._plan_docs.content_ids_for_plan(plan.uuid, item.user_id)
                or None
            )
        query = item.generation_prompt or item.title
        context = await _retrieve_context(
            self._retrieval,
            user_id=item.user_id,
            subject_id=subject_id,
            content_ids=content_ids,
            query=query,
            limit=6,
        )
        prompt = build_item_prompt(
            item_prompt=item.generation_prompt or item.title,
            context=context,
            plan_info=plan_info,
        )
        disabled = await self._providers.disabled_names()
        result = await self._gateway.generate(
            prompt, system=GENERATOR_SYSTEM, disabled=disabled
        )

        item.content = {"markdown": result.text, "provider": result.provider}
        item.generation_status = GenerationItemStatus.COMPLETED
        await self._session.commit()
        await self._recompute_run(item.generation_id)

    async def mark_item_failed(self, item_id: UUID, error: str) -> None:
        """Mark an item FAILED (worker, after exhausting retries)."""
        item = await self._repo.item_for_processing(item_id)
        if item is None:
            return
        item.generation_status = GenerationItemStatus.FAILED
        item.generation_error = error[:2000]
        await self._session.commit()
        if item.generation_id is not None:
            await self._recompute_run(item.generation_id)

    async def _recompute_run(self, generation_id: UUID) -> None:
        run = await self._repo.get_for_processing(generation_id)
        if run is None:
            return
        counts = await self._repo.item_status_counts(generation_id)
        in_flight = counts.get(GenerationItemStatus.PENDING, 0) + counts.get(
            GenerationItemStatus.PROCESSING, 0
        )
        if in_flight:
            run.status = GenerationRunStatus.RUNNING
        elif counts.get(GenerationItemStatus.FAILED, 0):
            run.status = GenerationRunStatus.PARTIAL
        else:
            run.status = GenerationRunStatus.COMPLETED
        await self._session.commit()
