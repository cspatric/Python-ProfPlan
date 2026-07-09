"""Unit tests for the LLM gateway fallback logic (no real providers)."""

import pytest

from app.modules.ai.domain.exceptions import (
    AllProvidersFailedError,
    ProviderUnavailableError,
)
from app.modules.ai.infrastructure.gateway.circuit_breaker import CircuitBreaker
from app.modules.ai.infrastructure.gateway.llm_gateway import LLMGateway


class FakeProvider:
    def __init__(
        self, name: str, *, text: str | None = None, error: Exception | None = None
    ) -> None:
        self.name = name
        self._text = text
        self._error = error
        self.calls = 0

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._text or ""


class FakeRedis:
    """A tiny in-memory stand-in for the handful of commands the breaker uses."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def incr(self, key: str) -> int:
        self.values[key] = str(int(self.values.get(key, "0")) + 1)
        return int(self.values[key])

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


def _breaker(name: str = "test") -> CircuitBreaker:
    return CircuitBreaker(FakeRedis(), name=name, failure_threshold=3, reset_seconds=30)


def _gateway(*providers: FakeProvider) -> LLMGateway:
    return LLMGateway([(p, _breaker(p.name)) for p in providers], max_concurrency=5)


async def test_uses_first_available_provider() -> None:
    claude = FakeProvider("claude", text="from claude")
    openai = FakeProvider("openai", text="from openai")
    gateway = _gateway(claude, openai)

    result = await gateway.generate("hi")

    assert result.provider == "claude"
    assert result.text == "from claude"
    assert openai.calls == 0


async def test_falls_back_to_openai_then_ollama() -> None:
    claude = FakeProvider("claude", error=ProviderUnavailableError("no key"))
    openai = FakeProvider("openai", error=RuntimeError("500"))
    ollama = FakeProvider("ollama", text="local answer")
    gateway = _gateway(claude, openai, ollama)

    result = await gateway.generate("hi")

    assert result.provider == "ollama"
    assert result.text == "local answer"
    assert claude.calls == 1 and openai.calls == 1 and ollama.calls == 1


async def test_all_providers_failing_raises() -> None:
    gateway = _gateway(
        FakeProvider("claude", error=RuntimeError("x")),
        FakeProvider("openai", error=RuntimeError("y")),
        FakeProvider("ollama", error=RuntimeError("z")),
    )

    with pytest.raises(AllProvidersFailedError) as exc:
        await gateway.generate("hi")
    assert set(exc.value.errors) == {"claude", "openai", "ollama"}


async def test_open_circuit_skips_provider() -> None:
    claude = FakeProvider("claude", text="unused")
    breaker = CircuitBreaker(
        FakeRedis(), name="claude", failure_threshold=1, reset_seconds=60
    )
    await breaker.record_failure()  # opens the circuit
    ollama = FakeProvider("ollama", text="fallback")
    gateway = LLMGateway(
        [(claude, breaker), (ollama, _breaker("ollama"))], max_concurrency=5
    )

    result = await gateway.generate("hi")

    assert result.provider == "ollama"
    assert claude.calls == 0  # skipped while open
