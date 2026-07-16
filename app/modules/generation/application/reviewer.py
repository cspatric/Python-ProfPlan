"""The LLM-judge tier of the roadmap evaluation.

Called by the planner only when the code checks in ``roadmap_eval`` flagged
something or the retrieved context was weak — a judge on every plan would
roughly double the planner's cost for the plans that were already fine.

Nothing here may fail a generation. A judge that errors, times out or answers
with garbage is a judge we ignore: the teacher gets the un-reviewed roadmap,
which is exactly what they would have got before this tier existed.
"""

import logging

from pydantic import ValidationError

from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.generation.domain.prompts import JUDGE_SYSTEM, build_judge_prompt
from app.modules.generation.domain.roadmap_eval import JudgeVerdict
from app.shared.ai.json_output import extract_json

logger = logging.getLogger("app.generation")


class RoadmapReviewer:
    """Asks an LLM to approve a roadmap or say what is wrong with it."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def review(
        self,
        *,
        roadmap_json: str,
        plan_info: str,
        teacher_input: str,
        context: str,
        code_issues: list[str],
        disabled: frozenset[str] | set[str] = frozenset(),
    ) -> JudgeVerdict | None:
        """Return the verdict, or None when the judge could not be trusted."""
        prompt = build_judge_prompt(
            roadmap_json=roadmap_json,
            plan_info=plan_info,
            teacher_input=teacher_input,
            context=context,
            code_issues=code_issues,
        )
        try:
            result = await self._gateway.generate(
                prompt, system=JUDGE_SYSTEM, disabled=disabled
            )
            verdict = JudgeVerdict.model_validate_json(extract_json(result.text))
        except (ValidationError, ValueError) as exc:
            logger.warning("roadmap judge returned an unusable verdict: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001 — the judge is best-effort
            logger.warning("roadmap judge failed: %s", exc)
            return None

        logger.info(
            "roadmap judged | approved=%s | issues=%d | provider=%s",
            verdict.approved,
            len(verdict.issues),
            result.provider,
        )
        return verdict
