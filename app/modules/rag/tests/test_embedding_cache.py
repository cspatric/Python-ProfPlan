"""Unit tests for the Redis-backed embedding cache."""

from typing import Any

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

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
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
