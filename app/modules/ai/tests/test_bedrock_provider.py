"""Reading Bedrock's Converse answer.

No network: what is worth pinning down is the shape of the response, because
that is what silently changes and what a wrong reading turns into a cost report
that no longer matches the invoice.

The provider is instantiated per model family (three of them ride this one
class), so these tests pass an explicit model rather than reading a global.
"""

import pytest

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
from app.modules.ai.domain.tiers import Tier
from app.modules.ai.infrastructure.providers.bedrock import BedrockProvider

ANSWER = {
    "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
    "stopReason": "end_turn",
    "usage": {
        "inputTokens": 13,
        "outputTokens": 4,
        "totalTokens": 17,
        "cacheReadInputTokens": 0,
        "cacheWriteInputTokens": 0,
    },
}


MODEL = "us.anthropic.claude-sonnet-5"
FAST_MODEL = "us.anthropic.claude-haiku-4-5"


def _provider(monkeypatch, answer=ANSWER, key="a-key"):
    settings = get_settings()
    monkeypatch.setattr(settings, "bedrock_api_key", key, raising=False)
    provider = BedrockProvider(name="claude", model=MODEL, fast_model=FAST_MODEL)
    captured: dict = {}

    async def _post(url, *, headers, json):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return answer

    monkeypatch.setattr(provider, "_post", _post)
    return provider, captured


async def test_the_answer_and_the_tokens_are_read(monkeypatch):
    provider, _ = _provider(monkeypatch)

    completion = await provider.generate("hello", system="be brief")

    assert completion.text == "ok"
    assert completion.usage.input_tokens == 13
    assert completion.usage.output_tokens == 4
    # Converse does not echo the model, and the profile id is what was billed.
    assert completion.model == MODEL


async def test_cached_tokens_are_counted_rather_than_dropped(monkeypatch):
    """They are billed, at a different rate, and they are reported apart.
    Dropping them would make the cost report quietly smaller than the bill."""
    answer = {
        **ANSWER,
        "usage": {
            "inputTokens": 10,
            "outputTokens": 4,
            "cacheReadInputTokens": 900,
            "cacheWriteInputTokens": 100,
        },
    }
    provider, _ = _provider(monkeypatch, answer)

    completion = await provider.generate("hello")

    assert completion.usage.input_tokens == 1010


async def test_the_system_prompt_is_a_field_not_a_message(monkeypatch):
    """Converse has a first-class `system`, which is what makes the models that
    distinguish the two actually treat it as one."""
    provider, captured = _provider(monkeypatch)

    await provider.generate("hello", system="be brief")

    assert captured["json"]["system"] == [{"text": "be brief"}]
    assert captured["json"]["messages"] == [
        {"role": "user", "content": [{"text": "hello"}]}
    ]
    assert captured["headers"]["Authorization"].startswith("Bearer ")


async def test_the_model_is_addressed_through_the_runtime_endpoint(monkeypatch):
    provider, captured = _provider(monkeypatch)

    await provider.generate("hello")

    settings = get_settings()
    assert captured["url"] == (
        f"https://bedrock-runtime.{settings.bedrock_region}.amazonaws.com"
        f"/model/{MODEL}/converse"
    )


async def test_an_empty_answer_is_a_failure_not_an_empty_plan(monkeypatch):
    """A refusal or a truncation comes back as a well-formed response with no
    text. Handing that on would put an empty plan in front of a teacher."""
    answer = {"output": {"message": {"content": []}}, "stopReason": "max_tokens"}
    provider, _ = _provider(monkeypatch, answer)

    with pytest.raises(ValueError, match="max_tokens"):
        await provider.generate("hello")


async def test_without_a_key_the_provider_says_so(monkeypatch):
    """So the gateway skips it and tries the next one, instead of failing the
    generation with an authentication error from AWS."""
    provider, _ = _provider(monkeypatch, key="")

    with pytest.raises(ProviderUnavailableError):
        await provider.generate("hello")


async def test_the_fast_tier_addresses_the_smaller_model_of_the_family(monkeypatch):
    """The chain picks the family, the tier picks the size within it: the same
    credential and the same endpoint host, a different model id."""
    provider, captured = _provider(monkeypatch)

    completion = await provider.generate("hello", tier=Tier.FAST)

    assert completion.model == FAST_MODEL
    assert f"/model/{FAST_MODEL}/converse" in captured["url"]


async def test_a_family_with_no_small_model_answers_everything_with_its_one(
    monkeypatch,
):
    """Falling back to the expensive model is a larger bill; falling back to
    nothing is a plan that never arrives."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bedrock_api_key", "a-key", raising=False)
    provider = BedrockProvider(name="claude", model=MODEL, fast_model="")

    async def _post(url, *, headers, json):
        return ANSWER

    monkeypatch.setattr(provider, "_post", _post)

    assert (await provider.generate("x", tier=Tier.FAST)).model == MODEL
