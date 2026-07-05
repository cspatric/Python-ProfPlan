"""Local Ollama chat provider (final fallback, no API key required)."""

from app.core.config import get_settings
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider


class OllamaProvider(HTTPLLMProvider):
    """Generates text via a local Ollama chat model."""

    name = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_chat_model

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        data = await self._post(
            f"{self._base_url}/api/chat",
            headers={"content-type": "application/json"},
            json={
                "model": self._model,
                "messages": self._messages(prompt, system),
                "stream": False,
            },
        )
        return data["message"]["content"]
