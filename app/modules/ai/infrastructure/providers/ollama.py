"""Local Ollama chat provider (final fallback, no API key required)."""

from app.core.config import get_settings
from app.modules.ai.domain.tiers import Tier
from app.modules.ai.domain.usage import Completion, TokenUsage
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider


class OllamaProvider(HTTPLLMProvider):
    """Generates text via a local Ollama chat model."""

    name = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_chat_model
        self._fast_model = settings.ollama_fast_model
        self._max_tokens = settings.llm_max_tokens

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tier: Tier = Tier.STANDARD,
    ) -> Completion:
        model = self._model_for(tier)
        data = await self._post(
            f"{self._base_url}/api/chat",
            headers={"content-type": "application/json"},
            json={
                "model": model,
                "messages": self._messages(prompt, system),
                "stream": False,
                # Bound the output (num_predict) and lower temperature so JSON
                # planning is faster and more deterministic on the local model.
                "options": {"num_predict": self._max_tokens, "temperature": 0.2},
            },
        )
        # Ollama reports the counts under different names, and reports them
        # even though the model is free: they are the only way to see that the
        # local fallback is doing the work the paid providers were not.
        return Completion(
            text=data["message"]["content"],
            model=data.get("model") or model,
            usage=TokenUsage(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            ),
        )
