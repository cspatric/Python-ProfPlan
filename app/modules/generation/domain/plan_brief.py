"""The plan's parameters in the two forms the planner needs them.

``info`` is the prose spliced into the prompt; ``classes`` is the same period
as a number, so the evaluation can tell whether the roadmap actually covers it.
Built from the payload on creation and from the persisted plan on a retrigger —
both paths must describe the plan identically, hence one builder.
"""

from dataclasses import dataclass
from datetime import date

from app.modules.generation.domain.roadmap_eval import expected_classes


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
) -> PlanBrief:
    """Describe a plan's period and cadence."""
    weeks = max((ends_at - starts_at).days, 0) / 7
    return PlanBrief(
        info=(
            f"Period: {starts_at} to {ends_at}. "
            f"{class_per_week} classes/week, {class_duration} min each."
        ),
        classes=expected_classes(weeks=weeks, class_per_week=class_per_week),
    )
