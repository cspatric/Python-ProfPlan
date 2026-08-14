"""Unit tests for the Redis-backed embedding cache."""

from typing import Any

from app.modules.rag.domain.interfaces import EmbedProgress
from app.modules.rag.infrastructure.embedding.cache import CachedEmbedding


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def mget_json(self, keys: list[str]) -> list[Any | None]:
        return [self.store.get(k) for k in keys]

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.store[key] = value


class CountingEmbedder:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    async def embed_texts(
        self, texts: list[str], *, on_progress: EmbedProgress | None = None
    ) -> list[list[float]]:
        self.embedded.extend(texts)
        if on_progress is not None:
            await on_progress(len(texts))
        return [[float(len(t))] for t in texts]

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


def make_cached() -> tuple[CachedEmbedding, CountingEmbedder]:
    embedder = CountingEmbedder()
    return CachedEmbedding(embedder, FakeCache(), "bge-m3"), embedder


async def test_miss_calls_model_then_hit_skips_it() -> None:
    cached, embedder = make_cached()

    first = await cached.embed_texts(["alpha", "beta"])
    assert embedder.embedded == ["alpha", "beta"]
    assert len(first) == 2

    # Second call for the same texts is served from cache.
    second = await cached.embed_texts(["alpha", "beta"])
    assert embedder.embedded == ["alpha", "beta"]  # unchanged: no new calls
    assert second == first


async def test_only_missing_texts_are_embedded() -> None:
    cached, embedder = make_cached()

    await cached.embed_texts(["alpha", "beta"])
    embedder.embedded.clear()

    await cached.embed_texts(["alpha", "gamma"])
    assert embedder.embedded == ["gamma"]  # only the new one


async def test_embed_text_uses_cache() -> None:
    cached, embedder = make_cached()

    await cached.embed_text("hello")
    await cached.embed_text("hello")
    assert embedder.embedded == ["hello"]


async def test_progress_counts_cache_hits_as_done() -> None:
    """A re-upload of a known document must not look stuck at zero.

    Its chunks are already in the cache, so it finishes in seconds. Reporting
    only what the model embedded would leave the bar at 0% until the very end.
    """
    cached, _ = make_cached()
    await cached.embed_texts(["a", "b"])  # warm the cache

    seen: list[int] = []
    await cached.embed_texts(["a", "b"], on_progress=lambda done: _record(seen, done))

    assert seen == [2]


async def test_progress_continues_from_the_cached_count() -> None:
    """The count is over the whole job, not over what the model did.

    Restarting from zero at the first fresh chunk would make the bar go
    backwards mid-document.
    """
    cached, _ = make_cached()
    await cached.embed_texts(["a"])  # only this one is cached

    seen: list[int] = []
    await cached.embed_texts(["a", "b"], on_progress=lambda done: _record(seen, done))

    assert seen == [1, 2]


async def _record(seen: list[int], done: int) -> None:
    seen.append(done)
