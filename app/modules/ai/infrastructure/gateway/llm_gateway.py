"""LLM gateway: try providers in order with per-provider circuit breakers.

Fallback chain (as designed): Claude → OpenAI → Gemini → Ollama. Each provider
is wrapped in a circuit breaker; a provider that is unavailable or fails (after
its own transient-error retries) is skipped and the next one is tried. If all
fail, ``AllProvidersFailedError`` is raised.
"""

import logging
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
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

    def __init__(self, providers: list[tuple[LLMProvider, CircuitBreaker]]) -> None:
        self._providers = providers

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
        errors: dict[str, str] = {}
        for provider, breaker in self._providers:
            if provider.name in disabled:
                errors[provider.name] = "disabled"
                continue
            if not breaker.allow():
                errors[provider.name] = "circuit_open"
                continue
            try:
                text = await provider.generate(prompt, system=system)
            except Exception as exc:  # noqa: BLE001 — any failure → next provider
                breaker.record_failure()
                errors[provider.name] = type(exc).__name__
                logger.warning("LLM provider %s failed: %s", provider.name, exc)
                continue
            breaker.record_success()
            return LLMResult(provider=provider.name, text=text)

        raise AllProvidersFailedError(errors)

    def provider_states(self) -> list[tuple[str, bool]]:
        """Return (provider name, circuit_open) in fallback order (for /health)."""
        return [
            (provider.name, breaker.is_open) for provider, breaker in self._providers
        ]


@lru_cache
def get_gateway() -> LLMGateway:
    """Build the shared gateway (breaker state persists per process)."""
    settings = get_settings()

    def _breaker() -> CircuitBreaker:
        return CircuitBreaker(
            failure_threshold=settings.llm_circuit_failure_threshold,
            reset_seconds=settings.llm_circuit_reset_seconds,
        )

    providers: list[tuple[LLMProvider, CircuitBreaker]] = [
        (ClaudeProvider(), _breaker()),
        (OpenAIProvider(), _breaker()),
        (GeminiProvider(), _breaker()),
        (OllamaProvider(), _breaker()),
    ]
    return LLMGateway(providers)
