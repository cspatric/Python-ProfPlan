"""RAG domain interfaces (ports)."""

from typing import Protocol


class Embedder(Protocol):
    """Produces embedding vectors for text (Ollama, cached, fakes, ...)."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_text(self, text: str) -> list[float]: ...
