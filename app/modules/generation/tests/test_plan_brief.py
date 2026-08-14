"""What the planner is told about the plan.

These fields only exist to change what the AI writes, so the test that matters
is whether they reach the prompt, and whether an empty one stays out of it: a
line reading "Audience: None" is read by the model as a fact about the class.
"""

from datetime import date

from app.modules.generation.domain.plan_brief import build_plan_brief
from app.modules.teaching_plans.domain.entities import PlanLevel

START, END = date(2026, 3, 1), date(2026, 4, 26)


def _brief(**kwargs) -> str:
    return build_plan_brief(
        starts_at=START,
        ends_at=END,
        class_per_week=2,
        class_duration=50,
        **kwargs,
    ).info


def test_period_and_cadence_are_always_described():
    info = _brief()

    assert "2026-03-01" in info
    assert "2026-04-26" in info
    assert "2 classes/week" in info
    assert "50 min" in info


def test_a_plan_with_only_dates_says_nothing_else():
    """The pre-existing behaviour: no invented facts about the class."""
    info = _brief()

    for word in ("Level", "Audience", "objectives", "already knows", "Resources"):
        assert word not in info


def test_each_field_reaches_the_prompt():
    info = _brief(
        level=PlanLevel.ADVANCED,
        audience="second-year undergraduates",
        objectives="derive and apply the quadratic formula",
        prior_knowledge="first-degree equations",
        resources="projector, no lab",
    )

    assert "second-year undergraduates" in info
    assert "derive and apply the quadratic formula" in info
    assert "first-degree equations" in info
    assert "projector, no lab" in info


def test_the_level_is_expanded_into_guidance():
    """The label alone is ambiguous; what it implies is what changes the plan."""
    introductory = _brief(level=PlanLevel.INTRODUCTORY)
    advanced = _brief(level=PlanLevel.ADVANCED)

    assert "no prior contact" in introductory
    assert "breadth over depth" in introductory
    assert "depth" in advanced
    assert introductory != advanced


def test_the_level_also_accepts_its_string_form():
    """Persisted rows come back as the raw enum value, not the member."""
    assert _brief(level="advanced") == _brief(level=PlanLevel.ADVANCED)


def test_blank_fields_are_left_out():
    info = _brief(audience="   ", objectives="", prior_knowledge=None)

    assert "Audience" not in info
    assert "objectives" not in info
    assert "already knows" not in info


def test_prior_knowledge_tells_the_planner_not_to_repeat_it():
    info = _brief(prior_knowledge="basic arithmetic")

    # The instruction, not just the fact: without it the planner happily
    # spends the first two weeks on what the class already knows.
    assert "do not re-teach" in info
    assert "basic arithmetic" in info


def test_the_class_count_is_unaffected_by_the_new_fields():
    plain = build_plan_brief(
        starts_at=START, ends_at=END, class_per_week=2, class_duration=50
    )
    detailed = build_plan_brief(
        starts_at=START,
        ends_at=END,
        class_per_week=2,
        class_duration=50,
        level=PlanLevel.ADVANCED,
        audience="anyone",
    )

    assert plain.classes == detailed.classes
