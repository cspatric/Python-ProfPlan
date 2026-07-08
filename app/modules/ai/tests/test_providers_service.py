"""Unit tests for AiProvidersService (status + toggle invariants + audit)."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.ai.application.providers_service import AiProvidersService
from app.modules.ai.domain.exceptions import (
    ProviderToggleError,
    UnknownProviderError,
)
from app.modules.audit.domain.entities import AuditAction

_CHAIN = ["claude", "openai", "gemini", "ollama"]


@dataclass
class FakeRow:
    name: str
    enabled: bool = True
    uuid: UUID = field(default_factory=uuid4)


class FakeRepo:
    def __init__(self) -> None:
        self.rows = {name: FakeRow(name) for name in _CHAIN}

    async def list_all(self) -> list[FakeRow]:
        return list(self.rows.values())

    async def get_by_name(self, name: str) -> FakeRow | None:
        return self.rows.get(name)


class FakeGateway:
    def provider_states(self) -> list[tuple[str, bool]]:
        return [(name, False) for name in _CHAIN]


class FakeSession:
    async def commit(self) -> None:
        pass


class FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


def _service(*, openai: str = "k", gemini: str = "k", claude: str = "") -> tuple:
    settings = SimpleNamespace(
        anthropic_api_key=claude, openai_api_key=openai, gemini_api_key=gemini
    )
    repo, audit = FakeRepo(), FakeAudit()
    service = AiProvidersService(FakeSession(), FakeGateway(), repo, settings, audit)
    return service, repo, audit


async def test_list_reports_configured_and_active() -> None:
    service, _, _ = _service(openai="k", gemini="k", claude="")
    by_name = {s.name: s for s in await service.list_all()}

    assert by_name["gemini"].configured and by_name["gemini"].active
    assert not by_name["claude"].configured  # no key
    assert by_name["ollama"].configured  # local, always configured
    assert by_name["openai"].order == 2


async def test_ollama_cannot_be_disabled() -> None:
    service, _, _ = _service()
    with pytest.raises(ProviderToggleError):
        await service.set_enabled("ollama", False)


async def test_unknown_provider_raises() -> None:
    service, _, _ = _service()
    with pytest.raises(UnknownProviderError):
        await service.set_enabled("mistral", False)


async def test_cannot_disable_the_last_active_non_ollama() -> None:
    # Only gemini is configured -> disabling it would leave only Ollama.
    service, _, _ = _service(openai="", gemini="k", claude="")
    with pytest.raises(ProviderToggleError):
        await service.set_enabled("gemini", False)


async def test_disable_persists_and_is_audited() -> None:
    service, repo, audit = _service(openai="k", gemini="k")
    statuses = {s.name: s for s in await service.set_enabled("gemini", False)}

    assert repo.rows["gemini"].enabled is False
    assert not statuses["gemini"].enabled
    assert statuses["openai"].active  # another non-ollama stays active
    assert audit.records and audit.records[0]["action"] == AuditAction.UPDATE
    assert audit.records[0]["entity"] == "ai_provider"
