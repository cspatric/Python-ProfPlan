"""Plan-generation use cases: plan (sync) -> fan-out (async) -> poll."""

from collections.abc import Mapping, Sequence
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
from app.modules.generation.domain.item_kinds import (
    ItemKind,
    is_graded,
    normalize_kind,
)
from app.modules.generation.domain.plan_brief import PlanBrief, build_plan_brief
from app.modules.generation.domain.prompts import (
    GENERATOR_SYSTEM,
    build_item_prompt,
)
from app.modules.generation.domain.roadmap import Roadmap
from app.modules.generation.domain.scheduling import schedule_items
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


def _brief(
    plan: Plan,
    *,
    item_counts: Mapping[ItemKind, int] | None = None,
    item_kinds: Sequence[ItemKind] | None = None,
) -> PlanBrief:
    """Describe a persisted plan exactly as the creation path described it.

    The worker generating each item reads this too, so an item is written for
    the same audience and level the roadmap was planned for. The composition
    is not on the plan, so the caller passes what the run recorded.
    """
    return build_plan_brief(
        starts_at=plan.starts_at,
        ends_at=plan.ends_at,
        class_per_week=plan.class_per_week,
        class_duration=plan.class_duration,
        level=plan.level,
        audience=plan.audience,
        objectives=plan.objectives,
        prior_knowledge=plan.prior_knowledge,
        resources=plan.resources,
        item_counts=item_counts,
        item_kinds=item_kinds,
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
        classes: int | None = None,
    ) -> Roadmap:
        """Run the planner agent (the synchronous AI call) and validate it.

        Validates subject ownership first (no AI tokens burned for an invalid
        subject) and anchors the planner on the subject's name. ``content_ids``
        scopes the RAG context to the documents selected for the plan;
        ``classes`` is how many classes the period holds, which lets the
        roadmap evaluation check the plan against it. Raises PlannerError (502)
        / AllProvidersFailedError (503) on failure — callers run this BEFORE
        persisting anything, so an AI failure surfaces as a real error and
        leaves no orphan rows behind.
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
            classes=classes,
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
        brief = _brief(plan)
        roadmap = await self.plan_roadmap(
            user_id=user_id,
            subject_id=plan.subject_id,
            plan_info=brief.info,
            teacher_input=teacher_input,
            content_ids=content_ids,
            classes=brief.classes,
        )
        return await self.materialize(
            user_id=user_id,
            plan=plan,
            roadmap=roadmap,
            teacher_input=teacher_input or self.default_input(),
        )

    async def begin(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        teacher_input: str | None,
        item_counts: Mapping[ItemKind, int] | None = None,
        item_kinds: Sequence[ItemKind] | None = None,
    ) -> PlanGeneration:
        """Open a run before the planner is called, and commit it.

        The row has to exist first so the request can answer with something to
        watch and a failure has somewhere to be recorded. Creating it only
        after a successful plan is what made the planner call have to be
        synchronous: nothing else could tell the caller that a plan was being
        drafted, or that the drafting had failed.
        """
        # The composition the teacher chose is not a column of the plan, so it
        # is kept with the run that has to honour it. Dropping it here would
        # quietly ignore "three exams" the moment the planner moved off the
        # request thread.
        run = PlanGeneration(
            plan_id=plan_id,
            user_id=user_id,
            status=GenerationRunStatus.PLANNING,
            input={
                "request": teacher_input,
                "counts": {kind.value: n for kind, n in (item_counts or {}).items()},
                "kinds": [kind.value for kind in (item_kinds or [])],
            },
        )
        self._repo.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def fail_run(self, run_id: UUID, error: str) -> None:
        """Record that a run could not be planned, with the reason."""
        run = await self._repo.get_for_processing(run_id)
        if run is None:
            return
        run.status = GenerationRunStatus.FAILED
        run.error = error[:2000]
        await self._session.commit()

    async def plan_existing_run(
        self, *, user_id: UUID, plan_id: UUID, run_id: UUID, teacher_input: str | None
    ) -> list[UUID]:
        """Draft the roadmap for an already-open run and materialise it.

        Returns the ids of the items to fan out. Called from the worker, which
        is where the planner call belongs: it costs up to a minute, and a
        request that spends a minute holding a connection open is a request
        that a dropped connection turns into a plan nobody can see.
        """
        plan = await self._plans.get_by_id(plan_id, user_id)
        if plan is None:
            raise PlanNotFoundError
        run = await self._repo.get_for_processing(run_id)
        if run is None:
            raise GenerationNotFoundError

        content_ids = (
            await self._plan_docs.content_ids_for_plan(plan_id, user_id) or None
        )
        asked = run.input or {}
        brief = _brief(
            plan,
            item_counts={
                ItemKind(kind): n for kind, n in (asked.get("counts") or {}).items()
            },
            item_kinds=[ItemKind(kind) for kind in (asked.get("kinds") or [])],
        )
        roadmap = await self.plan_roadmap(
            user_id=user_id,
            subject_id=plan.subject_id,
            plan_info=brief.info,
            teacher_input=teacher_input,
            content_ids=content_ids,
            classes=brief.classes,
        )
        _, items = await self.materialize(
            user_id=user_id,
            plan=plan,
            roadmap=roadmap,
            teacher_input=teacher_input or self.default_input(),
            run=run,
        )
        return [item.uuid for item in items]

    async def materialize(
        self,
        *,
        user_id: UUID,
        plan: Plan,
        roadmap: Roadmap,
        teacher_input: str,
        run: PlanGeneration | None = None,
    ) -> tuple[PlanGeneration, list[AcademicItem]]:
        """Persist a validated roadmap: run + modules + pending items.

        The caller enqueues one worker task per returned item. An existing
        `run` (opened by `begin`) is filled in rather than replaced, so the id
        the caller was already given stays the one to poll.
        """
        if run is None:
            run = PlanGeneration(
                plan_id=plan.uuid,
                user_id=user_id,
                input={"request": teacher_input},
            )
            self._repo.add(run)
        run.status = GenerationRunStatus.RUNNING
        run.roadmap = roadmap.model_dump()
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

            # Every item gets a real day: the planner's when it gave a usable
            # one, a computed slot inside the module otherwise.
            days = schedule_items(
                [item.date for item in planned_module.items], start=m_start, end=m_end
            )
            for planned_item, day in zip(planned_module.items, days, strict=True):
                kind = normalize_kind(planned_item.kind)
                item = AcademicItem(
                    user_id=user_id,
                    module_id=module.uuid,
                    created_by=user_id,
                    title=planned_item.title,
                    content=None,
                    generation_id=run.uuid,
                    generation_status=GenerationItemStatus.PENDING,
                    generation_prompt=planned_item.prompt,
                    # The shape the API and the frontend read (see
                    # AcademicItemMetadata): a day, and whether it is marked.
                    item_metadata={
                        "kind": kind.value,
                        "starts_at": day.isoformat(),
                        "ends_at": day.isoformat(),
                        "is_graded": is_graded(kind),
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
            plan_info = f"{subject_name}{_brief(plan).info}"
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
