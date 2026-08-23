"""Unit tests for the generation service (pure logic + mocked collaborators).

These do not touch an LLM or a database — the AI-dependent end-to-end path is
covered by the integration suite (skipped where no LLM is configured).
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.documents.domain.exceptions import DocumentNotFoundError
from app.modules.generation.application.service import (
    GenerationService,
    _split_period,
)
from app.modules.generation.domain.entities import (
    GenerationItemStatus,
    GenerationRunStatus,
)
from app.modules.generation.infrastructure.models import PlanGeneration
from app.modules.notifications.domain.entities import NotificationKind
from app.modules.teaching_plans.domain.exceptions import InvalidSubjectError


class TestSplitPeriod:
    """`_split_period` divides a plan's date range into contiguous module ranges."""

    def test_returns_one_range_per_module_covering_the_whole_period(self):
        start, end = date(2026, 8, 1), date(2026, 12, 15)
        ranges = _split_period(start, end, 4)

        assert len(ranges) == 4
        # First starts at the plan start, last ends at the plan end.
        assert ranges[0][0] == start
        assert ranges[-1][1] == end

    def test_ranges_are_contiguous_and_non_overlapping(self):
        ranges = _split_period(date(2026, 1, 1), date(2026, 1, 31), 3)

        for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:], strict=False):
            # The next module starts the day after the previous one ends.
            assert (next_start - prev_end).days == 1

    def test_zero_modules_yields_no_ranges(self):
        assert _split_period(date(2026, 1, 1), date(2026, 6, 1), 0) == []

    def test_single_module_spans_the_full_period(self):
        start, end = date(2026, 1, 1), date(2026, 3, 1)
        assert _split_period(start, end, 1) == [(start, end)]

    def test_more_modules_than_days_never_produces_inverted_ranges(self):
        ranges = _split_period(date(2026, 1, 1), date(2026, 1, 3), 10)

        assert len(ranges) == 10
        for seg_start, seg_end in ranges:
            assert seg_end >= seg_start


def _service(**overrides) -> GenerationService:
    """Build a service with dummy collaborators, overriding only what a test uses."""
    deps = {
        "gateway": None,
        "retrieval": None,
        "plans": None,
        "repo": None,
        "providers": None,
        "subjects": None,
        "plan_docs": None,
        "sources": None,
    }
    deps.update(overrides)
    return GenerationService(session=None, **deps)


class TestResolveDocuments:
    """Selected documents must belong to the user before a plan uses them."""

    async def test_empty_selection_returns_no_content_ids(self):
        service = _service()
        assert await service.resolve_documents(user_id=uuid4(), document_ids=[]) == []

    async def test_unowned_document_raises_not_found(self):
        doc_id = uuid4()

        class FakePlanDocs:
            async def owned_document_ids(self, ids, user_id):
                return set()  # user owns none of them

        service = _service(plan_docs=FakePlanDocs())
        with pytest.raises(DocumentNotFoundError):
            await service.resolve_documents(user_id=uuid4(), document_ids=[doc_id])

    async def test_owned_documents_resolve_to_their_content_ids(self):
        doc_id = uuid4()
        content_id = uuid4()

        class FakePlanDocs:
            async def owned_document_ids(self, ids, user_id):
                return {doc_id}

            async def content_ids_for_documents(self, ids, user_id):
                return [content_id]

        service = _service(plan_docs=FakePlanDocs())
        result = await service.resolve_documents(user_id=uuid4(), document_ids=[doc_id])
        assert result == [content_id]


class TestPlanRoadmapSubjectOwnership:
    """The planner validates subject ownership before spending any AI tokens."""

    async def test_missing_or_unowned_subject_raises_422(self):
        class FakeSubjects:
            async def get_by_id(self, subject_id, user_id):
                return None  # not owned / does not exist

        service = _service(subjects=FakeSubjects())
        with pytest.raises(InvalidSubjectError):
            await service.plan_roadmap(
                user_id=uuid4(),
                subject_id=uuid4(),
                plan_info="Period: ...",
            )

    async def test_default_input_is_non_empty(self):
        assert GenerationService.default_input().strip()


class TestRunCompletionNotifies:
    """Announcing a finished run.

    `_recompute_run` runs once per finished item, and only the last one moves
    the run out of RUNNING. The guard under test is what stops a forty-item
    plan from sending forty notifications — which is not a cosmetic problem: it
    is a bell nobody would ever open again.
    """

    @staticmethod
    def _run(status: GenerationRunStatus) -> PlanGeneration:
        return PlanGeneration(
            uuid=uuid4(), plan_id=uuid4(), user_id=uuid4(), status=status
        )

    def _service_for(self, run: PlanGeneration, counts: dict, subject_id=None):
        subject_id = subject_id or uuid4()

        class FakeRepo:
            async def get_for_processing(self, _id):
                return run

            async def item_status_counts(self, _id):
                return counts

        class FakePlans:
            async def get_for_processing(self, _id):
                return SimpleNamespace(subject_id=uuid4())

        class FakeSubjects:
            # The ownership-scoped read, not the worker one: a run already knows
            # whose it is, so the notification path filters by that owner rather
            # than looking one up.
            async def get_by_id(self, _subject_id, _user_id):
                # `uuid` as well as the name: the notification carries the
                # subject id so the alert can link to a plan, whose page is
                # nested under its subject.
                return SimpleNamespace(
                    uuid=subject_id, name="Biology", user_id=run.user_id
                )

        class FakeSession:
            async def commit(self):
                pass

        sent: list[dict] = []

        class FakeNotifier:
            def notify(self, **kwargs):
                sent.append(kwargs)

        service = _service(repo=FakeRepo(), plans=FakePlans(), subjects=FakeSubjects())
        service._session = FakeSession()
        service._notifier = FakeNotifier()
        return service, sent

    async def test_the_last_item_announces_a_ready_plan(self):
        run = self._run(GenerationRunStatus.RUNNING)
        subject_id = uuid4()
        service, sent = self._service_for(
            run, {GenerationItemStatus.COMPLETED: 8}, subject_id
        )

        await service._recompute_run(run.uuid)

        assert run.status is GenerationRunStatus.COMPLETED
        assert len(sent) == 1
        assert sent[0]["kind"] is NotificationKind.PLAN_READY
        # The subject's name, because a plan has no title of its own.
        assert sent[0]["params"]["subject_name"] == "Biology"
        # The subject id travels too, because a plan's page lives under it.
        assert sent[0]["params"]["subject_id"] == subject_id
        assert sent[0]["entity_id"] == run.plan_id

    async def test_an_item_still_in_flight_announces_nothing(self):
        run = self._run(GenerationRunStatus.RUNNING)
        service, sent = self._service_for(
            run,
            {GenerationItemStatus.COMPLETED: 3, GenerationItemStatus.PENDING: 5},
        )

        await service._recompute_run(run.uuid)

        assert run.status is GenerationRunStatus.RUNNING
        assert sent == []

    async def test_a_run_already_terminal_does_not_announce_again(self):
        # The idempotency that matters: a retried task recomputing a finished
        # run must not send a second alert about the same plan.
        run = self._run(GenerationRunStatus.COMPLETED)
        service, sent = self._service_for(run, {GenerationItemStatus.COMPLETED: 8})

        await service._recompute_run(run.uuid)

        assert sent == []

    async def test_some_failed_items_announce_a_partial_plan(self):
        run = self._run(GenerationRunStatus.RUNNING)
        service, sent = self._service_for(
            run,
            {GenerationItemStatus.COMPLETED: 6, GenerationItemStatus.FAILED: 2},
        )

        await service._recompute_run(run.uuid)

        assert run.status is GenerationRunStatus.PARTIAL
        assert sent[0]["kind"] is NotificationKind.PLAN_PARTIAL
        # How many failed, so the message can say what is missing.
        assert sent[0]["params"]["failed"] == 2

    async def test_without_a_notifier_the_run_still_finishes(self):
        run = self._run(GenerationRunStatus.RUNNING)
        service, _ = self._service_for(run, {GenerationItemStatus.COMPLETED: 4})
        service._notifier = None

        await service._recompute_run(run.uuid)

        assert run.status is GenerationRunStatus.COMPLETED
