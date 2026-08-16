"""Anthropic Claude provider."""

from typing import Any

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
from app.modules.ai.domain.tiers import Tier
from app.modules.ai.domain.usage import Completion, TokenUsage
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider

_ENDPOINT = "https://api.anthropic.com/v1/messages"


class ClaudeProvider(HTTPLLMProvider):
    """Generates text via the Anthropic Messages API."""

    name = "claude"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model
        self._fast_model = settings.anthropic_fast_model
        self._max_tokens = settings.llm_max_tokens

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tier: Tier = Tier.STANDARD,
    ) -> Completion:
        model = self._model_for(tier)
        if not self._api_key:
            raise ProviderUnavailableError("Anthropic API key not configured")
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        data = await self._post(
            _ENDPOINT,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        usage = data.get("usage") or {}
        return Completion(
            text=data["content"][0]["text"],
            # What answered, not what was asked for: Anthropic resolves an
            # alias to a dated model, and the dated one is what was billed.
            model=data.get("model") or model,
            usage=TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
            if usage
            else None,
        )
