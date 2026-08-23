"""Unit tests for AiProvidersService (status + toggle invariants + audit).

The names in the chain are model families, not vendors: claude, nova and openai
are all served by Amazon Bedrock and share one credential, and ollama is local.
That sharing is the thing worth pinning here — a missing Bedrock key does not
take out one link, it takes out every remote link at once.
"""

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

#: What build_gateway wires today: three Bedrock families, then the local floor.
_CHAIN = ["claude", "nova", "openai", "ollama"]


@dataclass
class FakeRow:
    name: str
    enabled: bool = True
    uuid: UUID = field(default_factory=uuid4)


class FakeRepo:
    def __init__(self, chain: list[str], disabled: set[str] | None = None) -> None:
        off = disabled or set()
        self.rows = {name: FakeRow(name, name not in off) for name in chain}

    async def list_all(self) -> list[FakeRow]:
        return list(self.rows.values())

    async def get_by_name(self, name: str) -> FakeRow | None:
        return self.rows.get(name)


class FakeGateway:
    def __init__(self, chain: list[str]) -> None:
        self._chain = chain

    async def provider_states(self) -> list[tuple[str, bool]]:
        return [(name, False) for name in self._chain]


class FakeSession:
    async def commit(self) -> None:
        pass


class FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


def _service(
    *,
    bedrock: str = "k",
    chain: list[str] | None = None,
    disabled: set[str] | None = None,
) -> tuple:
    """A service over `chain`, with a Bedrock key iff `bedrock` is truthy."""
    chain = chain or _CHAIN
    settings = SimpleNamespace(bedrock_api_key=bedrock)
    repo, audit = FakeRepo(chain, disabled), FakeAudit()
    service = AiProvidersService(
        FakeSession(), FakeGateway(chain), repo, settings, audit
    )
    return service, repo, audit


async def test_list_reports_configured_and_active() -> None:
    service, _, _ = _service(bedrock="k")
    by_name = {s.name: s for s in await service.list_all()}

    for family in ("claude", "nova", "openai"):
        assert by_name[family].configured and by_name[family].active
    assert by_name["ollama"].configured  # local, always configured
    assert by_name["claude"].order == 1
    assert by_name["ollama"].order == 4


async def test_one_missing_key_takes_out_every_remote_family() -> None:
    """The cost of one vendor: claude, nova and openai are all Bedrock, so they
    do not fail independently on credentials. Ollama is what is left."""
    service, _, _ = _service(bedrock="")
    by_name = {s.name: s for s in await service.list_all()}

    for family in ("claude", "nova", "openai"):
        assert not by_name[family].configured
        assert not by_name[family].active
    assert by_name["ollama"].active


async def test_ollama_cannot_be_disabled() -> None:
    service, _, _ = _service()
    with pytest.raises(ProviderToggleError):
        await service.set_enabled("ollama", False)


async def test_unknown_provider_raises() -> None:
    service, _, _ = _service()
    with pytest.raises(UnknownProviderError):
        await service.set_enabled("mistral", False)


async def test_cannot_disable_the_last_remote_family() -> None:
    """Turning off the last family that is not Ollama would leave every plan on
    the small local model, so the invariant refuses. This is what stops one API
    call from silently degrading the whole product."""
    service, _, _ = _service(bedrock="k", disabled={"claude", "nova"})
    with pytest.raises(ProviderToggleError):
        await service.set_enabled("openai", False)


async def test_disable_persists_and_is_audited() -> None:
    """Disabling one family is allowed while another remote one stays active —
    which is the reason the chain runs across three families and not one."""
    service, repo, audit = _service(bedrock="k")
    statuses = {s.name: s for s in await service.set_enabled("openai", False)}

    assert repo.rows["openai"].enabled is False
    assert not statuses["openai"].enabled
    assert statuses["claude"].active  # another family still answers
    assert audit.records and audit.records[0]["action"] == AuditAction.UPDATE
    assert audit.records[0]["entity"] == "ai_provider"
