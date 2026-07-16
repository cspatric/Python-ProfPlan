"""Prompts for the planner agent, its reviewer, and the per-item generator.

The planner prompt (the FIRST request sent to the AI when a plan is created)
lives in ``planner_prompt.md`` next to this module, so it can be edited without
touching code. It is loaded at call time and its tokens are replaced:
``[[PLAN_INFO]]``, ``[[TEACHER_INPUT]]`` and ``[[CONTEXT_BLOCK]]``.

The judge and repair prompts stay here: unlike the planner prompt they are
coupled to code (the verdict schema, the checks in ``roadmap_eval``), so editing
them in isolation would break the parse.
"""

from functools import lru_cache
from pathlib import Path

from app.shared.ai.prompt_safety import CONTEXT_SAFETY_RULE, wrap_untrusted_context

_PLANNER_PROMPT_FILE = Path(__file__).with_name("planner_prompt.md")
_TEMPLATE_DIVIDER = "\n---\n"

PLANNER_SYSTEM = (
    "You are a curriculum planning assistant for teachers. You design the "
    "roadmap of a teaching plan: which modules (units) it should have and which "
    "academic items (content, activities, assessments, bibliography, ...) each "
    "module needs. You do NOT write the content itself here — you only plan it. "
    "Respond in the same language as the teacher's input. " + CONTEXT_SAFETY_RULE
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
        "\n\nReference material from the teacher's documents:\n"
        + wrap_untrusted_context(context)
        if context
        else ""
    )
    return (
        _planner_template()
        .replace("[[PLAN_INFO]]", plan_info)
        .replace("[[TEACHER_INPUT]]", teacher_input)
        .replace("[[CONTEXT_BLOCK]]", context_block)
    )


JUDGE_SYSTEM = (
    "You are a strict reviewer of teaching-plan roadmaps. You do not rewrite the "
    "roadmap and you do not compliment it — you look for concrete problems and "
    "report them. Only report a problem you can point at in the roadmap itself; "
    "if the roadmap is usable, approve it. Respond with JSON only. "
    + CONTEXT_SAFETY_RULE
)


def build_judge_prompt(
    *,
    roadmap_json: str,
    plan_info: str,
    teacher_input: str,
    context: str,
    code_issues: list[str],
) -> str:
    """Ask the judge to approve the roadmap or list what is wrong with it."""
    context_block = (
        "\n\nReference material the roadmap was supposed to draw on:\n"
        + wrap_untrusted_context(context)
        if context
        else ""
    )
    flagged = (
        "\n\nAutomated checks already flagged the following. Confirm each one you "
        "agree with and drop the ones you consider false alarms:\n"
        + "\n".join(f"- {issue}" for issue in code_issues)
        if code_issues
        else ""
    )
    return (
        f"Review this teaching-plan roadmap against what was asked.\n\n"
        f"Plan parameters:\n{plan_info}\n\n"
        f"Teacher's request:\n{teacher_input}"
        f"{context_block}\n\n"
        f"Roadmap under review:\n<roadmap>\n{roadmap_json}\n</roadmap>"
        f"{flagged}\n\n"
        "Check, in this order:\n"
        "1. Does it deliver what the teacher asked for — is every explicit "
        "requirement (topic, date, activity, assessment) actually present?\n"
        "2. Does its size fit the period in the plan parameters?\n"
        "3. Is every item's `prompt` self-contained? A worker AI receives that "
        "prompt alone, with no access to this roadmap or the plan parameters.\n"
        "4. If reference material is shown above, is the roadmap consistent with "
        "it — nothing invented, nothing contradicted?\n\n"
        "Respond with a SINGLE valid JSON object and nothing else:\n\n"
        "{\n"
        '  "approved": true or false,\n'
        '  "issues": ["one concrete problem per entry, naming what to fix; '
        'empty when approved"]\n'
        "}\n\n"
        "Approve unless a problem would genuinely damage the plan — a roadmap "
        "that is merely not how you would have done it is approved. At most 5 "
        "issues."
    )


def build_repair_prompt(
    *,
    teacher_input: str,
    context: str,
    plan_info: str,
    roadmap_json: str,
    issues: list[str],
) -> str:
    """Re-run the planner with the reviewer's critique attached."""
    problems = "\n".join(f"- {issue}" for issue in issues)
    return (
        build_planner_prompt(
            teacher_input=teacher_input, context=context, plan_info=plan_info
        )
        + "\n\nYou already produced this roadmap:\n"
        f"<previous_roadmap>\n{roadmap_json}\n</previous_roadmap>\n\n"
        f"A reviewer rejected it for these reasons:\n{problems}\n\n"
        "Produce a corrected roadmap that fixes every problem above, keeping "
        "what was already good. Same JSON shape, JSON only."
    )


GENERATOR_SYSTEM = (
    "You are a teaching-content generator. You produce a single academic item "
    "(content, activity, assessment or bibliography) for a teaching plan, ready "
    "to use, grounded in the provided context when relevant. Respond in the same "
    "language as the request. Return well-structured Markdown. " + CONTEXT_SAFETY_RULE
)


def build_item_prompt(*, item_prompt: str, context: str, plan_info: str) -> str:
    """Prompt for generating one academic item's content."""
    context_block = (
        "\n\nReference material from the teacher's documents:\n"
        + wrap_untrusted_context(context)
        if context
        else ""
    )
    return (
        f"Teaching plan context:\n{plan_info}\n\n"
        f"Generate the following item:\n{item_prompt}"
        f"{context_block}"
    )
