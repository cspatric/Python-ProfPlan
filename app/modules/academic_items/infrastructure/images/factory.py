"""Assembling the figure resolver.

Kept in one place because the graph has a shape worth stating once: a public
search wrapped in a Redis cache, a bounded downloader, object storage, and the
repository that records the credit. The Redis client is passed in rather than
imported so a Celery task can hand over the client belonging to its own event
loop — the same reason the LLM gateway is built this way.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.redis.cache import RedisCache
from app.infrastructure.storage.minio import get_object_storage
from app.modules.academic_items.application.figure_service import FigureResolver
from app.modules.academic_items.infrastructure.figure_repository import (
    AcademicItemFigureRepository,
)
from app.modules.academic_items.infrastructure.images.cache import CachedImageSearch
from app.modules.academic_items.infrastructure.images.wikimedia import (
    ImageDownloader,
    WikimediaImageSearch,
)


def build_figure_resolver(session: AsyncSession, redis: Redis) -> FigureResolver:
    """A resolver backed by Wikimedia Commons, cached in Redis."""
    settings = get_settings()
    return FigureResolver(
        search=CachedImageSearch(
            WikimediaImageSearch(),
            RedisCache(redis, prefix="figures:"),
            ttl=settings.figure_cache_ttl_seconds,
        ),
        downloader=ImageDownloader(),
        storage=get_object_storage(),
        repo=AcademicItemFigureRepository(session),
    )
