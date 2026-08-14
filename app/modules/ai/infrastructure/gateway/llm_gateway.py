"""LLM gateway: try providers in order with per-provider circuit breakers.

Fallback chain (as designed): Claude → OpenAI → Gemini → Ollama. Each provider
is wrapped in a circuit breaker; a provider that is unavailable or fails (after
its own transient-error retries) is skipped and the next one is tried. If all
fail, ``AllProvidersFailedError`` is raised.
"""

import asyncio
import logging
import time
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.redis.client import redis_client
from app.infrastructure.telemetry.metrics import (
    LLM_ALL_PROVIDERS_FAILED,
    LLM_COST_USD,
    LLM_LATENCY_SECONDS,
    LLM_REQUESTS,
    LLM_TOKENS,
    LLM_UNPRICED,
)
from app.modules.ai.domain.exceptions import AllProvidersFailedError
from app.modules.ai.domain.interfaces import LLMProvider
from app.modules.ai.domain.pricing import cost_usd
from app.modules.ai.domain.usage import TokenUsage, record
from app.modules.ai.infrastructure.gateway.circuit_breaker import CircuitBreaker
from app.modules.ai.infrastructure.providers.claude import ClaudeProvider
from app.modules.ai.infrastructure.providers.gemini import GeminiProvider
from app.modules.ai.infrastructure.providers.ollama import OllamaProvider
from app.modules.ai.infrastructure.providers.openai import OpenAIProvider

logger = logging.getLogger("app.ai")


@dataclass(slots=True)
class LLMResult:
    """A successful generation, what produced it and what it cost."""

    provider: str
    text: str
    model: str = ""
    usage: TokenUsage | None = None
    #: None when the model has no price in the table, which is not the same as
    #: zero. See app/modules/ai/domain/pricing.py.
    cost_usd: float | None = None
    latency_seconds: float = 0.0


class LLMGateway:
    """Routes a prompt through the provider fallback chain."""

    def __init__(
        self,
        providers: list[tuple[LLMProvider, CircuitBreaker]],
        *,
        max_concurrency: int,
    ) -> None:
        self._providers = providers
        # Caps concurrent outbound calls process-wide: a burst of requests
        # queues here instead of each holding a DB connection open through an
        # unbounded number of simultaneous provider fallback chains.
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        disabled: AbstractSet[str] = frozenset(),
    ) -> LLMResult:
        """Return the first provider's completion, falling back on failure.

        Providers named in ``disabled`` (an admin turned them off — the caller
        loads this from the ai_provider table) are skipped, as are providers
        whose circuit breaker is open. The gateway itself stays stateless.
        """
        async with self._semaphore:
            errors: dict[str, str] = {}
            for provider, breaker in self._providers:
                if provider.name in disabled:
                    errors[provider.name] = "disabled"
                    LLM_REQUESTS.labels(provider.name, "disabled").inc()
                    continue
                if not await breaker.allow():
                    errors[provider.name] = "circuit_open"
                    LLM_REQUESTS.labels(provider.name, "circuit_open").inc()
                    continue
                started = time.perf_counter()
                try:
                    completion = await provider.generate(prompt, system=system)
                except Exception as exc:  # noqa: BLE001 — any failure → next provider
                    await breaker.record_failure()
                    errors[provider.name] = type(exc).__name__
                    LLM_REQUESTS.labels(provider.name, "failed").inc()
                    logger.warning("LLM provider %s failed: %s", provider.name, exc)
                    continue
                elapsed = time.perf_counter() - started
                await breaker.record_success()
                LLM_REQUESTS.labels(provider.name, "success").inc()
                return self._accounted(provider.name, completion, elapsed)

            LLM_ALL_PROVIDERS_FAILED.inc()
            raise AllProvidersFailedError(errors)

    @staticmethod
    def _accounted(provider: str, completion, elapsed: float) -> "LLMResult":
        """Count what this call used, then hand it back.

        Metrics and the ledger are both fed here, in the one place every
        successful call passes through. Doing it at the call sites instead
        would mean five of them, and the sixth one written next year.
        """
        model = completion.model or "unknown"
        usage = completion.usage
        price = cost_usd(model, usage)

        LLM_LATENCY_SECONDS.labels(provider, model).observe(elapsed)
        if usage is not None:
            LLM_TOKENS.labels(provider, model, "input").inc(usage.input_tokens)
            LLM_TOKENS.labels(provider, model, "output").inc(usage.output_tokens)
        if price is None:
            LLM_UNPRICED.labels(provider, model).inc()
        else:
            LLM_COST_USD.labels(provider, model).inc(price)

        record(model=model, usage=usage, cost_usd=price or 0.0)

        # One line per call, which is what makes "why did this plan cost that"
        # answerable in Loki after the fact. The prompt is deliberately absent:
        # it holds the teacher's material.
        logger.info(
            "llm call",
            extra={
                "llm_provider": provider,
                "llm_model": model,
                "llm_input_tokens": usage.input_tokens if usage else None,
                "llm_output_tokens": usage.output_tokens if usage else None,
                "llm_cost_usd": price,
                "llm_latency_seconds": round(elapsed, 3),
            },
        )
        return LLMResult(
            provider=provider,
            text=completion.text,
            model=model,
            usage=usage,
            cost_usd=price,
            latency_seconds=elapsed,
        )

    async def provider_states(self) -> list[tuple[str, bool]]:
        """Return (provider name, circuit_open) in fallback order (for /health)."""
        return [
            (provider.name, await breaker.is_open())
            for provider, breaker in self._providers
        ]


def build_gateway(redis) -> LLMGateway:
    """Build a gateway whose breaker state lives on the given Redis client.

    Celery tasks pass a per-run client (see ``new_redis_client``): breaker
    *state* still coordinates globally through Redis keys, but the connection
    belongs to the task's own event loop.
    """
    settings = get_settings()

    def _breaker(name: str) -> CircuitBreaker:
        return CircuitBreaker(
            redis,
            name=name,
            failure_threshold=settings.llm_circuit_failure_threshold,
            reset_seconds=settings.llm_circuit_reset_seconds,
        )

    claude, openai, gemini, ollama = (
        ClaudeProvider(),
        OpenAIProvider(),
        GeminiProvider(),
        OllamaProvider(),
    )
    providers: list[tuple[LLMProvider, CircuitBreaker]] = [
        (claude, _breaker(claude.name)),
        (openai, _breaker(openai.name)),
        (gemini, _breaker(gemini.name)),
        (ollama, _breaker(ollama.name)),
    ]
    return LLMGateway(providers, max_concurrency=settings.llm_max_concurrency)


@lru_cache
def get_gateway() -> LLMGateway:
    """The shared API-process gateway (single long-lived event loop)."""
    return build_gateway(redis_client)
