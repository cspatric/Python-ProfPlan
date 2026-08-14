"""RAG domain interfaces (ports)."""

from collections.abc import Awaitable, Callable
from typing import Protocol

#: Called with the number of texts embedded so far, as the work advances.
#:
#: Embedding a long document is minutes of work on a CPU, and without this the
#: only thing the app could say was "processing". With it, the page can show how
#: far along it is and, from the rate it is actually managing, how much longer
#: it will take.
EmbedProgress = Callable[[int], Awaitable[None]]


class Embedder(Protocol):
    """Produces embedding vectors for text (Ollama, cached, fakes, ...)."""

    async def embed_texts(
        self, texts: list[str], *, on_progress: EmbedProgress | None = None
    ) -> list[list[float]]: ...

    async def embed_text(self, text: str) -> list[float]: ...
