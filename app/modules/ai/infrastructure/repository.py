"""Persistence access for LLM provider configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.infrastructure.models import AiProvider


class AiProviderRepository:
    """Data-access for the ai_provider table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[AiProvider]:
        """Return every provider row (by name)."""
        result = await self._session.execute(
            select(AiProvider).order_by(AiProvider.name)
        )
        return list(result.scalars().all())

    async def disabled_names(self) -> set[str]:
        """Return the names of providers turned off.

        Disabled-set semantics (vs enabled): a provider without a row is treated
        as enabled, so a newly-added provider works until explicitly disabled.
        """
        result = await self._session.execute(
            select(AiProvider.name).where(AiProvider.enabled.is_(False))
        )
        return set(result.scalars().all())

    async def get_by_name(self, name: str) -> AiProvider | None:
        """Return a provider row by name."""
        result = await self._session.execute(
            select(AiProvider).where(AiProvider.name == name)
        )
        return result.scalar_one_or_none()
