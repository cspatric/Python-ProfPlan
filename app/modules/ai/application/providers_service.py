"""Use cases for inspecting and toggling the LLM providers.

Provider on/off state is stored in the ``ai_provider`` table (durable, the
single source of truth) and every toggle is written to the audit trail. API
keys are NOT here — they stay in the environment (see the module README).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.ai.domain.exceptions import (
    ProviderToggleError,
    UnknownProviderError,
)
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.audit.application.recorder import AuditRecorder
from app.modules.audit.domain.entities import AuditAction

_OLLAMA = "ollama"
_ENTITY = "ai_provider"


@dataclass(slots=True)
class ProviderStatus:
    """The runtime status of a single LLM provider."""

    name: str
    order: int
    configured: bool  # has an API key (Ollama is always configured, it's local)
    enabled: bool  # runtime toggle (ai_provider table)
    active: bool  # configured AND enabled -> can actually serve
    circuit_open: bool  # temporarily skipped after repeated failures


class AiProvidersService:
    """Lists provider status and enables/disables providers at runtime."""

    def __init__(
        self,
        session: AsyncSession,
        gateway: LLMGateway,
        repo: AiProviderRepository,
        settings: Settings,
        audit: AuditRecorder,
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._repo = repo
        self._settings = settings
        self._audit = audit

    def _configured(self, name: str) -> bool:
        return {
            "claude": bool(self._settings.anthropic_api_key),
            "openai": bool(self._settings.openai_api_key),
            "gemini": bool(self._settings.gemini_api_key),
            _OLLAMA: True,
        }.get(name, False)

    async def list_all(self) -> list[ProviderStatus]:
        """Return every provider's status, in fallback order."""
        enabled_by_name = {row.name: row.enabled for row in await self._repo.list_all()}
        statuses: list[ProviderStatus] = []
        for order, (name, circuit_open) in enumerate(
            self._gateway.provider_states(), start=1
        ):
            configured = self._configured(name)
            enabled = enabled_by_name.get(name, True)  # missing row -> enabled
            statuses.append(
                ProviderStatus(
                    name=name,
                    order=order,
                    configured=configured,
                    enabled=enabled,
                    active=configured and enabled,
                    circuit_open=circuit_open,
                )
            )
        return statuses

    async def set_enabled(self, name: str, enabled: bool) -> list[ProviderStatus]:
        """Enable/disable a provider, enforcing the fallback invariants + audit."""
        names = [n for n, _ in self._gateway.provider_states()]
        if name not in names:
            raise UnknownProviderError

        # Ollama is the offline safety net — it can never be turned off.
        if name == _OLLAMA and not enabled:
            raise ProviderToggleError(
                "Ollama is the offline fallback and cannot be disabled"
            )

        rows = {row.name: row for row in await self._repo.list_all()}
        enabled_after = {n: rows[n].enabled for n in rows}
        enabled_after[name] = enabled

        # There must always remain at least one active provider besides Ollama.
        active_non_ollama = [
            n
            for n in names
            if n != _OLLAMA and self._configured(n) and enabled_after.get(n, True)
        ]
        if not active_non_ollama:
            raise ProviderToggleError(
                "At least one provider besides Ollama must stay active"
            )

        provider = rows.get(name)
        if provider is None:
            raise UnknownProviderError
        old = provider.enabled
        provider.enabled = enabled
        self._audit.record(
            action=AuditAction.UPDATE,
            entity=_ENTITY,
            entity_id=provider.uuid,
            changes={"name": name, "enabled": {"old": old, "new": enabled}},
        )
        await self._session.commit()
        return await self.list_all()
