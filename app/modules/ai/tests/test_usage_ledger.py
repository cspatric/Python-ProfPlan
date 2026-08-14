"""The ledger that turns many calls into one plan's cost."""

import asyncio

from app.modules.ai.domain.usage import TokenUsage, record, usage_scope


def test_calls_add_up():
    with usage_scope() as ledger:
        record(model="claude-sonnet-5", usage=TokenUsage(100, 50), cost_usd=0.001)
        record(model="claude-sonnet-5", usage=TokenUsage(200, 80), cost_usd=0.002)

    assert ledger.calls == 2
    assert ledger.input_tokens == 300
    assert ledger.output_tokens == 130
    assert round(ledger.cost_usd, 6) == 0.003
    # One entry, not two: this is which models took part, not a call log.
    assert ledger.models == ["claude-sonnet-5"]


def test_the_models_that_answered_are_kept_in_order():
    """A plan that fell back mid-way costs what it costs because of this."""
    with usage_scope() as ledger:
        record(model="claude-sonnet-5", usage=TokenUsage(10, 10), cost_usd=0.1)
        record(model="llama3.2:3b", usage=TokenUsage(10, 10), cost_usd=0.0)

    assert ledger.models == ["claude-sonnet-5", "llama3.2:3b"]


def test_a_call_with_no_reported_tokens_still_counts_as_a_call():
    with usage_scope() as ledger:
        record(model="mystery", usage=None, cost_usd=0.0)

    assert ledger.calls == 1
    assert ledger.input_tokens == 0


def test_recording_outside_a_scope_is_not_an_error():
    """A health check or a script has no run to belong to. The metrics still
    see it; only the per-run total does not."""
    record(model="claude-sonnet-5", usage=TokenUsage(1, 1), cost_usd=0.1)


async def test_two_runs_at_the_same_time_do_not_mix():
    """The reason this is a ContextVar and not a module-level object: two
    plans drafted concurrently must not pay each other's bill."""

    async def draft(model: str, tokens: int, cost: float):
        with usage_scope() as ledger:
            record(model=model, usage=TokenUsage(tokens, tokens), cost_usd=cost)
            # Yield, so the two tasks are genuinely interleaved inside their
            # scopes rather than running one after the other.
            await asyncio.sleep(0)
            record(model=model, usage=TokenUsage(tokens, tokens), cost_usd=cost)
            return ledger

    first, second = await asyncio.gather(
        draft("claude-sonnet-5", 100, 0.01), draft("gpt-4o", 7, 0.002)
    )

    assert first.input_tokens == 200
    assert first.models == ["claude-sonnet-5"]
    assert second.input_tokens == 14
    assert second.models == ["gpt-4o"]
