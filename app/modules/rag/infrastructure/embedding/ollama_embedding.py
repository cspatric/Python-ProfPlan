"""Embedding provider backed by a local Ollama model (bge-m3).

One measured fact drives the shape of this file: on a CPU-only machine, bge-m3
takes roughly five seconds per chunk, and batching does not make it faster (a
batch of 64 costs about what 64 single calls cost). So a document of 154 chunks
is around thirteen minutes of work no matter how it is sliced.

What the slicing decides is whether it *finishes*. Sending all 154 chunks as
one HTTP request meant one thirteen-minute call against a sixty-second read
timeout: it could never succeed, and every large document failed. Sent in small
batches, each request completes well inside the timeout and the work simply
takes as long as it takes.
"""

import httpx

from app.core.config import get_settings
from app.modules.rag.domain.interfaces import EmbedProgress
from app.shared.decorators.retry import external_call


class OllamaEmbedding:
    """Generates embeddings by calling the Ollama `/api/embed` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        batch_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.ollama_base_url
        self._model = model or settings.embedding_model
        self._timeout = timeout or settings.embedding_timeout_seconds
        self._batch_size = batch_size or settings.embedding_batch_size

    async def embed_texts(
        self, texts: list[str], *, on_progress: EmbedProgress | None = None
    ) -> list[list[float]]:
        """Return an embedding vector for each input text, batch by batch."""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(await self._embed_batch(batch))
            if on_progress is not None:
                await on_progress(len(vectors))
        return vectors

    @external_call()
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """One request. Retried on its own, so a blip costs one batch, not all."""
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.post(
                "/api/embed", json={"model": self._model, "input": texts}
            )
            response.raise_for_status()
            return response.json()["embeddings"]

    async def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for a single text."""
        vectors = await self.embed_texts([text])
        return vectors[0]
