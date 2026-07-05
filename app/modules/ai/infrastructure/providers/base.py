"""Shared HTTP behaviour for LLM providers (with transient-error retry)."""

from typing import Any

import httpx

from app.shared.decorators.retry import external_call


class HTTPLLMProvider:
    """Base class doing a retried JSON POST to a provider's HTTP API."""

    name = "base"

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

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
