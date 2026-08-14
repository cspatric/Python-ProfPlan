"""The plan's parameters in the two forms the planner needs them.

``info`` is the prose spliced into the prompt; ``classes`` is the same period
as a number, so the evaluation can tell whether the roadmap actually covers it.
Built from the payload on creation and from the persisted plan on a retrigger,
both paths must describe the plan identically, hence one builder.

Everything past the period and cadence is optional. Only the fields the teacher
filled in reach the prompt: a line saying "Audience: None" would be worse than
no line at all, because the model reads it as a fact about the class.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.modules.generation.domain.item_kinds import ItemKind
from app.modules.generation.domain.roadmap_eval import expected_classes
from app.modules.teaching_plans.domain.entities import PlanLevel

# How each level should change what the planner writes. The label alone
# ("advanced") is ambiguous; saying what it implies is what makes the roadmap
# actually differ.
_LEVEL_GUIDANCE = {
    PlanLevel.INTRODUCTORY: (
        "introductory: assume no prior contact with the subject, define every "
        "term before using it, and favour breadth over depth"
    ),
    PlanLevel.INTERMEDIATE: (
        "intermediate: assume the basics are known, and spend the time on "
        "applying them rather than on re-deriving them"
    ),
    PlanLevel.ADVANCED: (
        "advanced: assume fluency with the fundamentals, go for depth, edge "
        "cases and open problems rather than coverage"
    ),
}


@dataclass(frozen=True, slots=True)
class PlanBrief:
    """Plan parameters for the planner prompt (``info``) and its eval."""

    info: str
    classes: int


def build_plan_brief(
    *,
    starts_at: date,
    ends_at: date,
    class_per_week: int,
    class_duration: int,
    level: PlanLevel | str | None = None,
    audience: str | None = None,
    objectives: str | None = None,
    prior_knowledge: str | None = None,
    resources: str | None = None,
    item_counts: Mapping[ItemKind, int] | None = None,
    item_kinds: Sequence[ItemKind] | None = None,
) -> PlanBrief:
    """Describe a plan's period, cadence and whatever else the teacher gave."""
    weeks = max((ends_at - starts_at).days, 0) / 7

    lines = [
        f"Period: {starts_at} to {ends_at}.",
        f"{class_per_week} classes/week, {class_duration} min each.",
    ]

    if level:
        parsed = PlanLevel(level) if not isinstance(level, PlanLevel) else level
        lines.append(f"Level: {_LEVEL_GUIDANCE[parsed]}.")
    if audience and audience.strip():
        lines.append(f"Audience: {audience.strip()}")
    if objectives and objectives.strip():
        lines.append("Learning objectives the plan must lead to: " + objectives.strip())
    if prior_knowledge and prior_knowledge.strip():
        lines.append(
            "The class already knows, do not re-teach it: " + prior_knowledge.strip()
        )
    if resources and resources.strip():
        lines.append(
            "Resources available, do not propose activities that need anything "
            "else: " + resources.strip()
        )

    # The composition the teacher asked for. Stated as a requirement rather
    # than a preference: a count the planner treats as a suggestion is a count
    # the teacher will have to fix by hand afterwards.
    if item_counts:
        wanted = ", ".join(
            f"exactly {count} of kind '{kind.value}'"
            for kind, count in item_counts.items()
            if count > 0
        )
        if wanted:
            lines.append(
                f"The plan must contain {wanted}, spread across the modules. "
                "This is a requirement, not a target."
            )

    if item_kinds:
        allowed = ", ".join(sorted({kind.value for kind in item_kinds}))
        lines.append(
            f"Use only these item kinds: {allowed}. Do not invent other kinds."
        )

    return PlanBrief(
        info=" ".join(lines[:2]) + ("\n" + "\n".join(lines[2:]) if lines[2:] else ""),
        classes=expected_classes(weeks=weeks, class_per_week=class_per_week),
    )
