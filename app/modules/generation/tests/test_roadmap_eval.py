"""Unit tests for the roadmap evaluation: code checks and the planner's tiers.

The point of the tiering is cost, so most of what is asserted here is *how many
LLM calls happened* for a given roadmap, not just the roadmap that came out.
"""

from datetime import date
from uuid import uuid4

from app.core.config import get_settings
from app.modules.generation.application.planner import PlannerAgent
from app.modules.generation.domain.plan_brief import build_plan_brief
from app.modules.generation.domain.roadmap import Roadmap
from app.modules.generation.domain.roadmap_eval import JudgeVerdict, check_roadmap

GOOD_PROMPT = (
    "Write the class content for a 50-minute lesson on cell theory for "
    "high-school students, covering the three postulates and ending with 3 "
    "review questions and their answers."
)


def _roadmap(*, items: int = 2, prompt: str = GOOD_PROMPT, titles=None) -> Roadmap:
    """A structurally valid roadmap; tests break the one field they care about."""
    return Roadmap(
        reasoning="About 8 classes in the period, so two modules of four.",
        summary="A four-week introduction to cell biology ending in a written test.",
        modules=[
            {
                "title": "The cell",
                "description": "Cell theory and organelles.",
                "items": [
                    {
                        "title": titles[i] if titles else f"Item {i}",
                        "kind": "conteudo",
                        "when": None,
                        "prompt": prompt,
                    }
                    for i in range(items)
                ],
            }
        ],
    )


class TestCheckRoadmap:
    """Tier 1: deterministic checks, no tokens."""

    def test_a_sane_roadmap_raises_nothing(self):
        assert check_roadmap(_roadmap(), classes=8) == []

    def test_flags_an_item_prompt_too_short_to_generate_from(self):
        issues = check_roadmap(_roadmap(prompt="Write about mitosis"), classes=8)
        assert any("too vague" in issue for issue in issues)

    def test_flags_duplicate_item_titles_case_insensitively(self):
        issues = check_roadmap(_roadmap(titles=["Mitosis", "MITOSIS"]), classes=8)
        assert any("Duplicate item titles" in issue for issue in issues)

    def test_flags_a_roadmap_that_does_not_cover_the_period(self):
        # 2 items for a full year of classes: the planner ignored the period.
        issues = check_roadmap(_roadmap(items=2), classes=80)
        assert any("does not cover the period" in issue for issue in issues)

    def test_flags_more_items_than_the_period_can_hold(self):
        issues = check_roadmap(_roadmap(items=30), classes=8)
        assert any("more than the period can hold" in issue for issue in issues)

    def test_sizing_is_skipped_when_the_period_is_unknown(self):
        assert check_roadmap(_roadmap(items=2), classes=None) == []

    def test_flags_a_summary_too_short_to_describe_the_plan(self):
        roadmap = _roadmap()
        roadmap.summary = "A plan."
        assert any("summary is too short" in i for i in check_roadmap(roadmap))


class FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.provider = "fake"


class FakeGateway:
    """Returns the queued answers in order, counting the calls."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.calls: list[str] = []

    async def generate(self, prompt, *, system=None, disabled=frozenset()):
        self.calls.append(prompt)
        return FakeResult(self._answers.pop(0))


class FakeRetrieval:
    """Stands in for the RAG search; distance drives the weak-context tier."""

    def __init__(self, *distances: float) -> None:
        self._distances = distances

    async def query(self, **kwargs):
        class Chunk:
            def __init__(self, distance):
                self.content = "some retrieved passage"
                self.distance = distance

        return [Chunk(d) for d in self._distances]


async def _plan(gateway, retrieval=None, *, classes=8) -> Roadmap:
    agent = PlannerAgent(gateway, retrieval or FakeRetrieval())
    return await agent.plan(
        user_id=uuid4(),
        subject_id=uuid4(),
        teacher_input="Introductory unit on the cell.",
        plan_info="Period: ...",
        classes=classes,
    )


class TestPlannerEvaluationTiers:
    """Tier 2 (the judge) must stay off the happy path."""

    async def test_a_clean_roadmap_costs_a_single_call(self):
        gateway = FakeGateway(_roadmap().model_dump_json())
        # Context close to the request: nothing for the judge to check.
        roadmap = await _plan(gateway, FakeRetrieval(0.1))

        assert len(gateway.calls) == 1
        assert roadmap.item_count() == 2

    async def test_code_issues_summon_the_judge(self):
        gateway = FakeGateway(
            _roadmap(prompt="Write about mitosis").model_dump_json(),
            JudgeVerdict(approved=True).model_dump_json(),
        )
        await _plan(gateway, FakeRetrieval(0.1))

        assert len(gateway.calls) == 2
        assert "Review this teaching-plan roadmap" in gateway.calls[1]

    async def test_weak_context_summons_the_judge_on_a_clean_roadmap(self):
        gateway = FakeGateway(
            _roadmap().model_dump_json(),
            JudgeVerdict(approved=True).model_dump_json(),
        )
        # Nothing retrieved is close to the request: the plan may float free.
        await _plan(gateway, FakeRetrieval(0.9))

        assert len(gateway.calls) == 2

    async def test_no_context_at_all_is_not_weak_context(self):
        gateway = FakeGateway(_roadmap().model_dump_json())
        await _plan(gateway, FakeRetrieval())  # no documents selected

        assert len(gateway.calls) == 1

    async def test_a_rejected_roadmap_is_repaired_once(self):
        repaired = _roadmap(items=3)
        gateway = FakeGateway(
            _roadmap(prompt="Write about mitosis").model_dump_json(),
            JudgeVerdict(
                approved=False, issues=["Item 0's prompt is not self-contained."]
            ).model_dump_json(),
            repaired.model_dump_json(),
        )
        roadmap = await _plan(gateway, FakeRetrieval(0.1))

        assert len(gateway.calls) == 3  # draft + judge + repair, never a 2nd judge
        assert "A reviewer rejected it" in gateway.calls[2]
        assert roadmap.item_count() == 3

    async def test_an_unusable_verdict_leaves_the_roadmap_alone(self):
        drafted = _roadmap(prompt="Write about mitosis")
        gateway = FakeGateway(drafted.model_dump_json(), "the judge rambled")
        roadmap = await _plan(gateway, FakeRetrieval(0.1))

        assert len(gateway.calls) == 2  # no repair attempted
        assert roadmap == drafted

    async def test_an_invalid_repair_leaves_the_roadmap_alone(self):
        drafted = _roadmap(prompt="Write about mitosis")
        gateway = FakeGateway(
            drafted.model_dump_json(),
            JudgeVerdict(approved=False, issues=["too vague"]).model_dump_json(),
            '{"summary": "no modules, no reasoning"}',
        )
        roadmap = await _plan(gateway, FakeRetrieval(0.1))

        assert roadmap == drafted

    async def test_the_eval_can_be_switched_off(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "planner_eval_enabled", False)
        gateway = FakeGateway(_roadmap(prompt="Write about mitosis").model_dump_json())

        await _plan(gateway, FakeRetrieval(0.9))

        assert len(gateway.calls) == 1  # would have been judged twice over


class TestDraftRetry:
    """An invalid draft is retried with the reason, not a generic scolding."""

    async def test_the_retry_carries_the_validation_error(self):
        gateway = FakeGateway("not json at all", _roadmap().model_dump_json())
        await _plan(gateway, FakeRetrieval(0.1))

        # Draft + retried draft. No judge: the retried roadmap came out clean.
        assert len(gateway.calls) == 2
        assert "your previous answer was rejected" in gateway.calls[1]


class TestPlanBrief:
    """The period must reach the eval as a number, from both entry points."""

    def test_counts_the_classes_the_period_holds(self):
        brief = build_plan_brief(
            starts_at=date(2026, 3, 2),
            ends_at=date(2026, 3, 27),
            class_per_week=2,
            class_duration=50,
        )
        assert brief.classes == 7  # ~3.57 weeks x 2
        assert "2 classes/week" in brief.info

    def test_a_single_day_plan_still_holds_one_class(self):
        brief = build_plan_brief(
            starts_at=date(2026, 3, 2),
            ends_at=date(2026, 3, 2),
            class_per_week=2,
            class_duration=50,
        )
        assert brief.classes == 1
