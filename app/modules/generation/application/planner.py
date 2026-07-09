"""Planner agent: turns the teacher's request into a structured roadmap.

This is the single SYNCHRONOUS LLM call. It returns a validated `Roadmap`
(modules + items, each with its own sub-prompt); the per-item generation is
fanned out to workers afterwards.
"""

import logging
from uuid import UUID

from pydantic import ValidationError

from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.generation.domain.exceptions import PlannerError
from app.modules.generation.domain.prompts import (
    PLANNER_SYSTEM,
    build_planner_prompt,
)
from app.modules.generation.domain.roadmap import Roadmap
from app.modules.rag.application.retrieval_service import RetrievalService

logger = logging.getLogger("app.generation")


def _extract_json(text: str) -> str:
    """Pull the JSON object out of an LLM answer (tolerates fences/prose)."""
    text = text.strip()
    if "```" in text:
        # take the content of the first fenced block
        parts = text.split("```")
        if len(parts) >= 2:
            block = parts[1]
            block = block[4:] if block.lower().startswith("json") else block
            text = block.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise PlannerError("planner did not return a JSON object")
    return text[start : end + 1]


class PlannerAgent:
    """Produces the roadmap for a plan generation."""

    def __init__(self, gateway: LLMGateway, retrieval: RetrievalService) -> None:
        self._gateway = gateway
        self._retrieval = retrieval

    async def plan(
        self,
        *,
        user_id: UUID,
        subject_id: UUID | None,
        teacher_input: str,
        plan_info: str,
        content_ids: list[UUID] | None = None,
        disabled: frozenset[str] | set[str] = frozenset(),
        retries: int = 1,
    ) -> Roadmap:
        """Retrieve context, ask the LLM, validate the roadmap (retry once)."""
        try:
            chunks = await self._retrieval.query(
                user_id=user_id,
                query=teacher_input,
                subject_id=subject_id,
                content_ids=content_ids,
                limit=8,
            )
            context = "\n\n".join(
                f"[{i + 1}] {c.content}" for i, c in enumerate(chunks)
            )
        except Exception:  # noqa: BLE001 — context is best-effort
            context = ""

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            prompt = build_planner_prompt(
                teacher_input=teacher_input, context=context, plan_info=plan_info
            )
            if attempt > 0:
                prompt += (
                    "\n\nIMPORTANT: your previous answer was not valid JSON. "
                    "Return ONLY the JSON object, nothing else."
                )
            result = await self._gateway.generate(
                prompt, system=PLANNER_SYSTEM, disabled=disabled
            )
            try:
                return Roadmap.model_validate_json(_extract_json(result.text))
            except (PlannerError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "planner attempt %d invalid: %s | provider=%s | raw=%.300s",
                    attempt,
                    exc,
                    result.provider,
                    result.text,
                )

        raise PlannerError(f"planner failed to produce a valid roadmap: {last_error}")
