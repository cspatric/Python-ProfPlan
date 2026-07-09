"""Unit tests for the generation service (pure logic + mocked collaborators).

These do not touch an LLM or a database — the AI-dependent end-to-end path is
covered by the integration suite (skipped where no LLM is configured).
"""

from datetime import date
from uuid import uuid4

import pytest

from app.modules.documents.domain.exceptions import DocumentNotFoundError
from app.modules.generation.application.service import (
    GenerationService,
    _split_period,
)
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
