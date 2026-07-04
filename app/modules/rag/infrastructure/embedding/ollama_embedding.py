"""Embedding provider backed by a local Ollama model (bge-m3)."""

import httpx

from app.core.config import get_settings
from app.shared.decorators.retry import external_call


class OllamaEmbedding:
    """Generates embeddings by calling the Ollama `/api/embed` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.ollama_base_url
        self._model = model or settings.embedding_model
        self._timeout = timeout

    @external_call()
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return an embedding vector for each input text (single request)."""
        if not texts:
            return []
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
