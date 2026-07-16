"""Evaluation of the planner's roadmap, cheapest tier first.

Judging every roadmap with an LLM would roughly double the planner's token
cost, so the evaluation is two-tiered:

1. ``check_roadmap`` — deterministic checks, zero tokens, runs on every plan.
2. The LLM judge (``prompts.build_judge_prompt``) — only called when tier 1
   flags something or the RAG context came back weak.

The checks here are deliberately loose. They exist to catch a roadmap that is
obviously broken (a planner that ignored the period, items no worker could
generate from), not to have an opinion on pedagogy — that is the judge's job,
and false alarms here cost real tokens downstream.
"""

from pydantic import BaseModel, Field

from app.modules.generation.domain.roadmap import Roadmap


class JudgeVerdict(BaseModel):
    """What the LLM judge returned about a roadmap (tier 2)."""

    approved: bool
    issues: list[str] = Field(default_factory=list, max_length=5)


# A prompt shorter than this cannot be self-contained: the worker AI receives it
# without the roadmap, so "Write about mitosis" produces a generic wall of text.
MIN_ITEM_PROMPT_CHARS = 80
MIN_SUMMARY_CHARS = 40

# Bounds on item count vs the classes the period holds. Items are not 1:1 with
# classes (one content item can span several; a class can hold two items), so
# these only fire when the planner disregarded the period altogether.
MIN_ITEMS_PER_CLASS = 0.25
MAX_ITEMS_PER_CLASS = 1.5


def expected_classes(*, weeks: float, class_per_week: int) -> int:
    """How many classes the plan's period holds (used to size the roadmap)."""
    return max(1, round(weeks * class_per_week))


def check_roadmap(roadmap: Roadmap, *, classes: int | None = None) -> list[str]:
    """Return the problems found in the roadmap; empty means it looks sane.

    ``classes`` is how many classes the period holds; pass None to skip the
    sizing check.
    """
    issues: list[str] = []

    if len(roadmap.summary) < MIN_SUMMARY_CHARS:
        issues.append("The summary is too short to describe the plan.")

    seen: dict[str, int] = {}
    for module in roadmap.modules:
        for item in module.items:
            if len(item.prompt) < MIN_ITEM_PROMPT_CHARS:
                issues.append(
                    f"Item '{item.title}' has a prompt of only {len(item.prompt)} "
                    "characters — too vague for a worker to generate from without "
                    "seeing the roadmap."
                )
            key = item.title.strip().casefold()
            seen[key] = seen.get(key, 0) + 1

    duplicates = sorted(title for title, count in seen.items() if count > 1)
    if duplicates:
        issues.append(f"Duplicate item titles: {', '.join(duplicates)}.")

    if classes:
        count = roadmap.item_count()
        if count < classes * MIN_ITEMS_PER_CLASS:
            issues.append(
                f"Only {count} items for a period of about {classes} classes — "
                "the plan does not cover the period."
            )
        elif count > classes * MAX_ITEMS_PER_CLASS:
            issues.append(
                f"{count} items for a period of about {classes} classes — "
                "more than the period can hold."
            )

    return issues
