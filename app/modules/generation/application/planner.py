"""Planner agent: turns the teacher's request into a structured roadmap.

This is the single SYNCHRONOUS LLM call path. It returns a validated `Roadmap`
(modules + items, each with its own sub-prompt); the per-item generation is
fanned out to workers afterwards.

Three steps, and only the first always costs tokens:

    draft  -> the planner writes the roadmap (retried on invalid output)
    eval   -> code checks always; the LLM judge only when they flag something
              or the retrieved context was too weak to have grounded the plan
    repair -> one re-plan with the judge's critique, when the judge rejects

So a plan that comes out clean still costs exactly one call, as before. The
worst case is three. Evaluation never fails a generation — if the judge cannot
run, or its repair is invalid, the teacher gets the roadmap we had.
"""

import logging
from uuid import UUID

from pydantic import ValidationError

from app.core.config import get_settings
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.generation.application.reviewer import RoadmapReviewer
from app.modules.generation.domain.exceptions import PlannerError
from app.modules.generation.domain.language import PlanLanguage
from app.modules.generation.domain.prompts import (
    build_planner_prompt,
    build_repair_prompt,
    planner_system,
)
from app.modules.generation.domain.roadmap import Roadmap
from app.modules.generation.domain.roadmap_eval import check_roadmap
from app.modules.rag.application.retrieval_service import RetrievalService
from app.shared.ai.json_output import extract_json

logger = logging.getLogger("app.generation")


class PlannerAgent:
    """Produces the roadmap for a plan generation."""

    def __init__(
        self,
        gateway: LLMGateway,
        retrieval: RetrievalService,
        reviewer: RoadmapReviewer | None = None,
    ) -> None:
        self._gateway = gateway
        self._retrieval = retrieval
        self._reviewer = reviewer or RoadmapReviewer(gateway)

    async def plan(
        self,
        *,
        user_id: UUID,
        subject_id: UUID | None,
        teacher_input: str,
        plan_info: str,
        content_ids: list[UUID] | None = None,
        classes: int | None = None,
        disabled: frozenset[str] | set[str] = frozenset(),
        retries: int = 1,
        language: PlanLanguage | None = None,
    ) -> Roadmap:
        """Retrieve context, draft the roadmap, evaluate it, repair if rejected.

        ``classes`` is how many classes the plan's period holds; it lets the
        evaluation catch a roadmap that ignored the period.
        """
        context, weak_context = await self._context(
            user_id=user_id,
            subject_id=subject_id,
            query=teacher_input,
            content_ids=content_ids,
        )
        roadmap = await self._draft(
            teacher_input=teacher_input,
            context=context,
            plan_info=plan_info,
            disabled=disabled,
            retries=retries,
            language=language,
        )
        return await self._evaluated(
            roadmap,
            teacher_input=teacher_input,
            context=context,
            weak_context=weak_context,
            plan_info=plan_info,
            classes=classes,
            disabled=disabled,
            language=language,
        )

    async def _context(
        self,
        *,
        user_id: UUID,
        subject_id: UUID | None,
        query: str,
        content_ids: list[UUID] | None,
    ) -> tuple[str, bool]:
        """Return the RAG context and whether it was too weak to ground a plan.

        Weak means chunks came back but none of them is actually close to the
        request — the planner will have written around them. Having no chunks
        at all is not weak: nothing was expected to ground the plan, so there is
        nothing for a judge to check.
        """
        try:
            chunks = await self._retrieval.query(
                user_id=user_id,
                query=query,
                subject_id=subject_id,
                content_ids=content_ids,
                limit=8,
            )
        except Exception:  # noqa: BLE001 — context is best-effort
            return "", False
        if not chunks:
            return "", False
        context = "\n\n".join(f"[{i + 1}] {c.content}" for i, c in enumerate(chunks))
        closest = min(c.distance for c in chunks)
        weak = closest > get_settings().planner_weak_context_distance
        if weak:
            logger.info("planner context is weak | closest_distance=%.3f", closest)
        return context, weak

    async def _draft(
        self,
        *,
        teacher_input: str,
        context: str,
        plan_info: str,
        disabled: frozenset[str] | set[str],
        retries: int,
        language: PlanLanguage | None,
    ) -> Roadmap:
        """Ask the planner for a roadmap until it validates (or give up)."""
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            prompt = build_planner_prompt(
                teacher_input=teacher_input, context=context, plan_info=plan_info
            )
            if last_error is not None:
                # Hand the model the actual reason, not a generic "be valid":
                # a missing field and unparseable JSON need different fixes.
                prompt += (
                    f"\n\nIMPORTANT: your previous answer was rejected: "
                    f"{last_error}\nReturn ONLY the JSON object described above, "
                    "with every field present."
                )
            result = await self._gateway.generate(
                prompt, system=planner_system(language), disabled=disabled
            )
            try:
                return Roadmap.model_validate_json(extract_json(result.text))
            except (ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "planner attempt %d invalid: %s | provider=%s | raw=%.300s",
                    attempt,
                    exc,
                    result.provider,
                    result.text,
                )

        raise PlannerError(f"planner failed to produce a valid roadmap: {last_error}")

    async def _evaluated(
        self,
        roadmap: Roadmap,
        *,
        teacher_input: str,
        context: str,
        weak_context: bool,
        plan_info: str,
        classes: int | None,
        disabled: frozenset[str] | set[str],
        language: PlanLanguage | None,
    ) -> Roadmap:
        """Run the evaluation tiers; return the repaired roadmap, or the original."""
        if not get_settings().planner_eval_enabled:
            return roadmap

        issues = check_roadmap(roadmap, classes=classes)
        if not issues and not weak_context:
            return roadmap  # clean and grounded: the judge has nothing to earn

        logger.info(
            "roadmap sent to the judge | code_issues=%d | weak_context=%s",
            len(issues),
            weak_context,
        )
        roadmap_json = roadmap.model_dump_json()
        verdict = await self._reviewer.review(
            roadmap_json=roadmap_json,
            plan_info=plan_info,
            teacher_input=teacher_input,
            context=context,
            code_issues=issues,
            disabled=disabled,
        )
        if verdict is None or verdict.approved:
            return roadmap

        return await self._repair(
            roadmap,
            issues=verdict.issues,
            roadmap_json=roadmap_json,
            teacher_input=teacher_input,
            context=context,
            plan_info=plan_info,
            disabled=disabled,
            language=language,
        )

    async def _repair(
        self,
        roadmap: Roadmap,
        *,
        issues: list[str],
        roadmap_json: str,
        teacher_input: str,
        context: str,
        plan_info: str,
        disabled: frozenset[str] | set[str],
        language: PlanLanguage | None,
    ) -> Roadmap:
        """Re-plan once with the critique attached; keep the original on failure.

        The repaired roadmap is not judged again: a second round would double the
        cost for a shrinking return, and the first critique is the one that
        carried the real problems.
        """
        prompt = build_repair_prompt(
            teacher_input=teacher_input,
            context=context,
            plan_info=plan_info,
            roadmap_json=roadmap_json,
            issues=issues,
        )
        try:
            result = await self._gateway.generate(
                prompt, system=planner_system(language), disabled=disabled
            )
            repaired = Roadmap.model_validate_json(extract_json(result.text))
        except (ValidationError, ValueError) as exc:
            logger.warning("roadmap repair produced invalid output: %s", exc)
            return roadmap
        except Exception as exc:  # noqa: BLE001 — repair is best-effort
            logger.warning("roadmap repair failed: %s", exc)
            return roadmap

        logger.info("roadmap repaired after review | issues=%d", len(issues))
        return repaired
