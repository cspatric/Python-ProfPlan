"""What a generation cost, and where that gets added up.

Two things live here.

**`TokenUsage` and `Completion`** are what a provider now returns. A provider
used to return a string, which is everything the application needs and nothing
the person paying for it needs: the same plan can cost half a cent or thirty,
depending on which model in the fallback chain answered, and a string cannot
say which.

**`UsageLedger`** adds those up across a whole run. One plan is not one call:
it is a planner call, sometimes a repair, sometimes a judge, and then one call
per activity, spread over several worker tasks. The ledger is carried in a
`ContextVar` rather than passed down through every signature, for the same
reason a request id is: it is ambient to the work, every layer in between would
only be forwarding it, and a parameter that four functions pass along without
reading is a parameter that will be forgotten in the fifth.

`ContextVar` is the right tool and not a global: asyncio gives each task its
own copy, so two plans drafted at the same time cannot add to each other's
total.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What one call consumed, as the provider reported it."""

    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class Completion:
    """One provider's answer, with the model that produced it.

    `usage` is optional because it is the provider's to report: a response that
    arrives without it is still a perfectly good completion, and inventing a
    token count by guessing would put a number nobody can act on into a cost
    report. Missing is counted as missing, see `LLM_UNPRICED` in the gateway.
    """

    text: str
    model: str
    usage: TokenUsage | None = None


@dataclass(slots=True)
class UsageLedger:
    """Running total for one unit of work, usually one plan."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    #: Which models took part, in the order they first answered. Kept because
    #: "this plan cost 4 cents" is not actionable without "on which model".
    models: list[str] = field(default_factory=list)

    def add(self, *, model: str, usage: TokenUsage | None, cost_usd: float) -> None:
        self.calls += 1
        if usage is not None:
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens
        self.cost_usd += cost_usd
        if model not in self.models:
            self.models.append(model)


_current: ContextVar[UsageLedger | None] = ContextVar("llm_usage_ledger", default=None)


@contextmanager
def usage_scope() -> Iterator[UsageLedger]:
    """Collect the cost of every LLM call made inside this block.

    Nesting is allowed and the inner scope wins; the outer one simply does not
    see the inner calls. Nothing nests today, and an inner scope silently
    doubling a total would be worse than one that under-reports visibly.
    """
    ledger = UsageLedger()
    token = _current.set(ledger)
    try:
        yield ledger
    finally:
        _current.reset(token)


def record(*, model: str, usage: TokenUsage | None, cost_usd: float) -> None:
    """Add one call to the ledger in scope, if there is one.

    Outside a scope this does nothing, on purpose: the metrics are recorded by
    the gateway regardless, and a call made outside any run (a health check, a
    script) has no run to belong to.
    """
    ledger = _current.get()
    if ledger is not None:
        ledger.add(model=model, usage=usage, cost_usd=cost_usd)
