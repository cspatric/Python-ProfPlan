"""Redis-backed cache in front of an embedding provider.

Embedding is the expensive step (a call to the bge-m3 model). Identical text —
e.g. a repeated RAG question or re-processed chunk — is served from Redis
instead of hitting the model again.
"""

import hashlib

from app.core.config import get_settings
from app.infrastructure.redis.cache import RedisCache
from app.infrastructure.redis.client import redis_client
from app.modules.rag.domain.interfaces import Embedder
from app.modules.rag.infrastructure.embedding.ollama_embedding import (
    OllamaEmbedding,
)


class CachedEmbedding:
    """Wraps an embedder, caching vectors in Redis keyed by (model, text)."""

    def __init__(self, embedder: Embedder, cache: RedisCache, model: str) -> None:
        self._embedder = embedder
        self._cache = cache
        self._model = model

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self._model}:{digest}"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        keys = [self._key(text) for text in texts]
        results: list[list[float] | None] = await self._cache.mget_json(keys)

        missing = [i for i, cached in enumerate(results) if cached is None]
        if missing:
            fresh = await self._embedder.embed_texts([texts[i] for i in missing])
            for index, vector in zip(missing, fresh, strict=True):
                results[index] = vector
                await self._cache.set_json(keys[index], vector)

        return [vector for vector in results if vector is not None]

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


def build_cached_embedder() -> CachedEmbedding:
    """Build the default cached embedder (Ollama + Redis)."""
    settings = get_settings()
    cache = RedisCache(
        redis_client,
        prefix="embedding:",
        ttl=settings.embedding_cache_ttl_seconds,
    )
    return CachedEmbedding(OllamaEmbedding(), cache, settings.embedding_model)
