"""What the models charge.

A price list in code is a fact about the world that goes stale on a day nobody
notices, so two rules keep it honest.

**Nothing is guessed.** A model that is not in the table is not priced at an
average or at zero: its tokens are still counted, its cost is `None`, and the
gateway raises a counter for it. A cost report that is quietly wrong is worse
than one that says "I do not know what this model costs", because only the
second one gets fixed.

**Prefixes, not exact names.** Providers append dates and revisions
(`claude-sonnet-5-20260114`, `gpt-4o-2026-05-13`) and the price does not change
with them. The longest matching prefix wins, so a specifically priced variant
beats its family.

Prices are USD per **million** tokens, list price, as published in August 2026.
They are not read at runtime from anywhere: a deployment that wants different
numbers, a negotiated rate or a different currency, overrides them here in one
place and the tests say what broke.
"""

import logging

from app.modules.ai.domain.usage import TokenUsage

logger = logging.getLogger("app.ai")

#: model prefix -> (input USD per 1M tokens, output USD per 1M tokens)
PRICES_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    # Anthropic, direct.
    #
    # The Sonnet family price here is the 4.x list price. Sonnet 5 through
    # Bedrock is cheaper (see below), which is evidence that the direct price
    # for it is lower too, and evidence is not a number: check Anthropic's
    # price page before running the direct provider on Sonnet 5, because a
    # priced-but-wrong model is worse than an unpriced one, and the unpriced
    # alert will not fire for it.
    "claude-opus": (15.00, 75.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),
    # Anthropic, through Bedrock. Same list price, different id: Bedrock keeps
    # the vendor in the model name, and the routing prefix is stripped before
    # this table is consulted.
    "anthropic.claude-opus": (15.00, 75.00),
    "anthropic.claude-sonnet": (3.00, 15.00),
    "anthropic.claude-haiku": (1.00, 5.00),
    # Sonnet 5 is not priced like the 4.x family, and this is not from memory:
    # it is the rate card on the model's own agreement offer, read with
    # ListFoundationModelAgreementOffers. us-east-1 on demand is 2.20 and
    # 11.00; through the *global* profile it is 2.00 and 10.00. The routing
    # prefix is stripped before this table is read, so the dearer of the two is
    # quoted, which errs toward over-reporting. For a cost report that is the
    # right direction to be wrong in.
    "anthropic.claude-sonnet-5": (2.20, 11.00),
    # Other Bedrock families, so a fallback to one of them is not silently
    # unpriced.
    "amazon.nova-pro": (0.80, 3.20),
    "amazon.nova-lite": (0.06, 0.24),
    "amazon.nova-micro": (0.035, 0.14),
    "meta.llama3": (0.72, 0.72),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    # Google
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    # Google also serves rolling aliases, and they are what a deployment
    # usually configures. They are priced as whatever they currently point at;
    # the day that changes, the alert on unpriced calls does not fire, so this
    # line is the one to re-read when a bill surprises somebody.
    "gemini-flash-lite-latest": (0.10, 0.40),
    "gemini-flash-latest": (0.30, 2.50),
    "gemini-pro-latest": (1.25, 10.00),
}

#: Models that run on hardware already paid for. Zero is the true price here,
#: not a missing one, and the difference matters: the fallback chain ending on
#: Ollama is the cheap outcome, not the unknown one.
LOCAL_MODEL_PREFIXES = ("llama", "qwen", "mistral", "phi", "gemma", "deepseek")


#: Bedrock addresses a model through an inference profile, so the id that was
#: billed carries a routing prefix: `us.`, `eu.`, `apac.`, `global.`. The
#: prefix decides which region serves the request, not what it costs, so it is
#: removed before pricing. (Bedrock's list price does vary by region for some
#: models; the day that matters here, this is the line to split.)
_ROUTING_PREFIXES = ("us.", "eu.", "apac.", "global.", "us-gov.")


def _without_routing(model: str) -> str:
    for prefix in _ROUTING_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def cost_usd(model: str, usage: TokenUsage | None) -> float | None:
    """What this call cost, or None when the model is not in the table.

    None and 0.0 are different answers and both are meaningful: 0.0 is a local
    model, None is "somebody added a model and nobody added its price".
    """
    if usage is None:
        return None

    name = _without_routing(model.strip().lower())
    if any(name.startswith(prefix) for prefix in LOCAL_MODEL_PREFIXES):
        return 0.0

    matches = [prefix for prefix in PRICES_USD_PER_MILLION if name.startswith(prefix)]
    if not matches:
        return None

    # Longest prefix wins: "gpt-4o-mini" must not be priced as "gpt-4o".
    price_in, price_out = PRICES_USD_PER_MILLION[max(matches, key=len)]
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
