"""AI domain interfaces (ports)."""

from typing import Protocol


class LLMProvider(Protocol):
    """A large-language-model text generator (Claude, OpenAI, Ollama, ...)."""

    name: str

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Return the model's completion for the prompt."""
        ...
