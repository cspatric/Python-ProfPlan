"""Google Gemini provider (Generative Language API)."""

from typing import Any

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(HTTPLLMProvider):
    """Generates text via the Google Gemini API (`generateContent`)."""

    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._max_tokens = settings.llm_max_tokens

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("Gemini API key not configured")

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self._max_tokens,
                "temperature": 0.2,
            },
        }
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}

        data = await self._post(
            f"{_BASE}/{self._model}:generateContent?key={self._api_key}",
            headers={"content-type": "application/json"},
            json=body,
        )
        # Guard against empty/truncated candidates (e.g. the thinking budget
        # consuming maxOutputTokens) so the gateway sees a clear failure
        # instead of a KeyError.
        candidates = data.get("candidates") or []
        content = candidates[0].get("content") if candidates else None
        parts = (content or {}).get("parts")
        text = parts[0].get("text", "") if parts else ""
        if not text:
            reason = (
                candidates[0].get("finishReason") if candidates else "NO_CANDIDATES"
            )
            raise ValueError(f"Gemini returned no text (finishReason={reason})")
        return text
