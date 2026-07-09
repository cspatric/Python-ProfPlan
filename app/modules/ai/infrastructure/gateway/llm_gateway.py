"""LLM gateway: try providers in order with per-provider circuit breakers.

Fallback chain (as designed): Claude → OpenAI → Gemini → Ollama. Each provider
is wrapped in a circuit breaker; a provider that is unavailable or fails (after
its own transient-error retries) is skipped and the next one is tried. If all
fail, ``AllProvidersFailedError`` is raised.
"""

import asyncio
import logging
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.redis.client import redis_client
from app.modules.ai.domain.exceptions import AllProvidersFailedError
from app.modules.ai.domain.interfaces import LLMProvider
from app.modules.ai.infrastructure.gateway.circuit_breaker import CircuitBreaker
from app.modules.ai.infrastructure.providers.claude import ClaudeProvider
from app.modules.ai.infrastructure.providers.gemini import GeminiProvider
from app.modules.ai.infrastructure.providers.ollama import OllamaProvider
from app.modules.ai.infrastructure.providers.openai import OpenAIProvider

logger = logging.getLogger("app.ai")


@dataclass(slots=True)
class LLMResult:
    """A successful generation and which provider produced it."""

    provider: str
    text: str


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
                    continue
                if not await breaker.allow():
                    errors[provider.name] = "circuit_open"
                    continue
                try:
                    text = await provider.generate(prompt, system=system)
                except Exception as exc:  # noqa: BLE001 — any failure → next provider
                    await breaker.record_failure()
                    errors[provider.name] = type(exc).__name__
                    logger.warning("LLM provider %s failed: %s", provider.name, exc)
                    continue
                await breaker.record_success()
                return LLMResult(provider=provider.name, text=text)

            raise AllProvidersFailedError(errors)

    async def provider_states(self) -> list[tuple[str, bool]]:
        """Return (provider name, circuit_open) in fallback order (for /health)."""
        return [
            (provider.name, await breaker.is_open())
            for provider, breaker in self._providers
        ]


@lru_cache
def get_gateway() -> LLMGateway:
    """Build the shared gateway (Redis-backed breaker state, shared process-wide)."""
    settings = get_settings()

    def _breaker(name: str) -> CircuitBreaker:
        return CircuitBreaker(
            redis_client,
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
