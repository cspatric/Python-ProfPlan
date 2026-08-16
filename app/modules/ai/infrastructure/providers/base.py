"""Shared HTTP behaviour for LLM providers (with transient-error retry)."""

from typing import Any

import httpx

from app.modules.ai.domain.tiers import Tier
from app.shared.decorators.retry import external_call


class HTTPLLMProvider:
    """Base class doing a retried JSON POST to a provider's HTTP API."""

    name = "base"

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        # Subclasses set these; declared here so `_model_for` can rely on them.
        self._model = ""
        self._fast_model = ""

    def _model_for(self, tier: Tier) -> str:
        """The model this provider answers a call of this tier with.

        A provider with no cheap model configured answers everything with its
        one model. That is deliberate: falling back to the expensive model is a
        larger bill, and falling back to nothing is a plan that never arrives.
        """
        if tier is Tier.FAST and self._fast_model:
            return self._fast_model
        return self._model

    @external_call()
    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=json)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages
