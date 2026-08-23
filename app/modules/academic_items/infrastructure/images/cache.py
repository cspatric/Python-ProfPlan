"""Redis cache in front of an image search.

The same description recurs constantly — "a labelled diagram of a neuron" is
wanted by the content item, the exercise list and the exam of the same module —
and a forty-item plan would otherwise be forty round trips to a public API that
asks to be used sparingly. Caching the *search result* rather than the image
means a second item reuses the object already in MinIO instead of downloading
and storing the same picture twice.

Only non-empty results are cached, and that asymmetry is deliberate: "nothing
found" is often a description the model will phrase better next time, and
remembering the miss for a week would freeze that.
"""

import hashlib
from dataclasses import asdict

from app.infrastructure.redis.cache import RedisCache
from app.modules.academic_items.domain.figures import (
    FigureCandidate,
    FigureSource,
)
from app.modules.academic_items.domain.interfaces import ImageSearch


class CachedImageSearch:
    """Wraps an image search, caching candidate lists in Redis by query."""

    def __init__(self, search: ImageSearch, cache: RedisCache, *, ttl: int) -> None:
        self._search = search
        self._cache = cache
        self._ttl = ttl

    @staticmethod
    def _key(query: str) -> str:
        digest = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
        return f"figure:{digest}"

    async def search(self, query: str, *, limit: int = 5) -> list[FigureCandidate]:
        key = self._key(query)
        cached = await self._cache.get_json(key)
        if cached:
            return [_from_dict(entry) for entry in cached][:limit]

        candidates = await self._search.search(query, limit=limit)
        if candidates:
            await self._cache.set_json(
                key, [asdict(c) for c in candidates], ttl=self._ttl
            )
        return candidates


def _from_dict(entry: dict) -> FigureCandidate:
    return FigureCandidate(**{**entry, "source": FigureSource(entry["source"])})
