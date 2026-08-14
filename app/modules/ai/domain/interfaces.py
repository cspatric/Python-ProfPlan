"""AI domain interfaces (ports)."""

from typing import Protocol

from app.modules.ai.domain.usage import Completion


class LLMProvider(Protocol):
    """A large-language-model text generator (Claude, OpenAI, Ollama, ...)."""

    name: str

    async def generate(self, prompt: str, *, system: str | None = None) -> Completion:
        """Return the model's completion, with the tokens it reported using."""
        ...
