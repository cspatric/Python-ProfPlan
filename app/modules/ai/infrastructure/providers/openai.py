"""OpenAI (ChatGPT) provider."""

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider

_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(HTTPLLMProvider):
    """Generates text via the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model
        self._max_tokens = settings.llm_max_tokens

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("OpenAI API key not configured")
        data = await self._post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "messages": self._messages(prompt, system),
                "max_tokens": self._max_tokens,
            },
        )
        return data["choices"][0]["message"]["content"]
