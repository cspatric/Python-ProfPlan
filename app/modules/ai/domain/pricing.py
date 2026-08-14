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
    # Anthropic
    "claude-opus": (15.00, 75.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),
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


def cost_usd(model: str, usage: TokenUsage | None) -> float | None:
    """What this call cost, or None when the model is not in the table.

    None and 0.0 are different answers and both are meaningful: 0.0 is a local
    model, None is "somebody added a model and nobody added its price".
    """
    if usage is None:
        return None

    name = model.strip().lower()
    if any(name.startswith(prefix) for prefix in LOCAL_MODEL_PREFIXES):
        return 0.0

    matches = [prefix for prefix in PRICES_USD_PER_MILLION if name.startswith(prefix)]
    if not matches:
        return None

    # Longest prefix wins: "gpt-4o-mini" must not be priced as "gpt-4o".
    price_in, price_out = PRICES_USD_PER_MILLION[max(matches, key=len)]
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
