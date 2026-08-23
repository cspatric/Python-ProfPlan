"""Redis-backed cache in front of an embedding provider.

Embedding is the expensive step (a call to the bge-m3 model). Identical text —
e.g. a repeated RAG question or re-processed chunk — is served from Redis
instead of hitting the model again.
"""

import hashlib

from redis.asyncio import Redis

from app.core.config import get_settings
from app.infrastructure.redis.cache import RedisCache
from app.infrastructure.redis.client import redis_client
from app.modules.rag.domain.interfaces import Embedder, EmbedProgress
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

    async def embed_texts(
        self, texts: list[str], *, on_progress: EmbedProgress | None = None
    ) -> list[list[float]]:
        if not texts:
            return []
        keys = [self._key(text) for text in texts]
        results: list[list[float] | None] = await self._cache.mget_json(keys)

        missing = [i for i, cached in enumerate(results) if cached is None]

        # What the cache already had is done work, and saying so keeps a
        # re-upload of a known document from looking stuck at zero while it
        # finishes in seconds.
        cached_count = len(texts) - len(missing)
        if on_progress is not None and cached_count:
            await on_progress(cached_count)

        if missing:
            inner = (
                None
                if on_progress is None
                else lambda done: on_progress(cached_count + done)
            )
            fresh = await self._embedder.embed_texts(
                [texts[i] for i in missing], on_progress=inner
            )
            for index, vector in zip(missing, fresh, strict=True):
                results[index] = vector
            # One pipelined batch per group instead of a round trip per chunk:
            # a large document is thousands of vectors, and writing them one at
            # a time is thousands of sequential waits on the network.
            await self._cache.set_many_json(
                [(keys[index], results[index]) for index in missing]
            )

        return [vector for vector in results if vector is not None]

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


def build_cached_embedder(redis: Redis | None = None) -> CachedEmbedding:
    """Build the cached embedder (Ollama + Redis).

    ``redis`` defaults to the API's shared client. Celery tasks pass their
    per-run client so cache connections belong to the task's own event loop
    (see ``app/infrastructure/redis/client.py``).
    """
    settings = get_settings()
    cache = RedisCache(
        redis if redis is not None else redis_client,
        prefix="embedding:",
        ttl=settings.embedding_cache_ttl_seconds,
        batch_size=settings.redis_batch_size,
    )
    return CachedEmbedding(OllamaEmbedding(), cache, settings.embedding_model)
