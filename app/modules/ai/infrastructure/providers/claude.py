"""Anthropic Claude provider."""

from typing import Any

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
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
        self._max_tokens = settings.llm_max_tokens

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("Anthropic API key not configured")
        payload: dict[str, Any] = {
            "model": self._model,
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
        return data["content"][0]["text"]
