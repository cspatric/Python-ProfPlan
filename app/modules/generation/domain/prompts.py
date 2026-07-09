"""Prompts for the planner agent and the per-item generator agent.

The planner prompt (the FIRST request sent to the AI when a plan is created)
lives in ``planner_prompt.md`` next to this module, so it can be edited without
touching code. It is loaded at call time and its tokens are replaced:
``[[PLAN_INFO]]``, ``[[TEACHER_INPUT]]`` and ``[[CONTEXT_BLOCK]]``.
"""

from functools import lru_cache
from pathlib import Path

_PLANNER_PROMPT_FILE = Path(__file__).with_name("planner_prompt.md")
_TEMPLATE_DIVIDER = "\n---\n"

PLANNER_SYSTEM = (
    "You are a curriculum planning assistant for teachers. You design the "
    "roadmap of a teaching plan: which modules (units) it should have and which "
    "academic items (content, activities, assessments, bibliography, ...) each "
    "module needs. You do NOT write the content itself here — you only plan it. "
    "Respond in the same language as the teacher's input."
)


@lru_cache
def _planner_template() -> str:
    """Load the planner prompt template (everything after the divider)."""
    raw = _PLANNER_PROMPT_FILE.read_text(encoding="utf-8")
    # The header (title + editing instructions) stays out of the prompt.
    _, _, template = raw.partition(_TEMPLATE_DIVIDER)
    return template.strip() or raw.strip()


def build_planner_prompt(*, teacher_input: str, context: str, plan_info: str) -> str:
    """Fill the markdown template with the plan info, request and RAG context."""
    context_block = (
        f"\n\nReference material from the teacher's documents:\n{context}"
        if context
        else ""
    )
    return (
        _planner_template()
        .replace("[[PLAN_INFO]]", plan_info)
        .replace("[[TEACHER_INPUT]]", teacher_input)
        .replace("[[CONTEXT_BLOCK]]", context_block)
    )


GENERATOR_SYSTEM = (
    "You are a teaching-content generator. You produce a single academic item "
    "(content, activity, assessment or bibliography) for a teaching plan, ready "
    "to use, grounded in the provided context when relevant. Respond in the same "
    "language as the request. Return well-structured Markdown."
)


def build_item_prompt(*, item_prompt: str, context: str, plan_info: str) -> str:
    """Prompt for generating one academic item's content."""
    context_block = (
        f"\n\nReference material from the teacher's documents:\n{context}"
        if context
        else ""
    )
    return (
        f"Teaching plan context:\n{plan_info}\n\n"
        f"Generate the following item:\n{item_prompt}"
        f"{context_block}"
    )
