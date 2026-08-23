"""The price table, and the two answers it must keep apart.

`None` means "nobody priced this model" and `0.0` means "this model is free".
Collapsing them is the failure this file exists to prevent: an unpriced model
counted as free makes a cost report that is quietly missing the expensive half.

Every remote model here is a Bedrock id, because Bedrock is the only remote
provider. A model from a vendor this application does not integrate with must
come back unpriced rather than guessed.
"""

from app.modules.ai.domain.pricing import cost_usd
from app.modules.ai.domain.usage import TokenUsage

MILLION = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)


def test_a_priced_model_costs_what_the_table_says():
    # anthropic.claude-sonnet-5 is 2.20 in and 11.00 out per million.
    assert cost_usd("us.anthropic.claude-sonnet-5", MILLION) == 13.20


def test_the_dated_variant_is_priced_like_its_family():
    """Bedrock appends a date and a revision to the model that answered, and
    the price does not change with it."""
    assert cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", MILLION) == 6.60


def test_the_longest_prefix_wins():
    """Sonnet 5 has its own rate card and must not be billed at the 4.x family
    price, which is 50 percent dearer."""
    assert cost_usd("anthropic.claude-sonnet-5", MILLION) == 13.20
    assert cost_usd("anthropic.claude-sonnet-4-6", MILLION) == 19.80


def test_a_local_model_is_free_rather_than_unknown():
    assert cost_usd("llama3.2:3b", MILLION) == 0.0


def test_an_unknown_model_has_no_price_at_all():
    """Not zero. Zero would be a lie that balances the books."""
    assert cost_usd("some-new-model-nobody-priced", MILLION) is None


def test_a_route_we_do_not_have_is_unpriced():
    """Every remote call goes through Bedrock, so a direct-vendor id cannot be
    produced by this system. If one ever appears in the ledger, something is
    calling a route that was removed, and an unpriced call is how that shows."""
    assert cost_usd("gpt-4o", MILLION) is None  # not on Bedrock at all
    assert cost_usd("gemini-2.5-flash", MILLION) is None  # no Bedrock route
    assert cost_usd("claude-sonnet-5", MILLION) is None  # direct, not via Bedrock


def test_the_openai_family_is_counted_but_not_yet_priced():
    """gpt-oss is reachable (it is in the chain) and its rate card has not been
    read yet, so it must report tokens with no cost rather than a guess. This
    test is the reminder: when the price lands in the table, it fails."""
    assert cost_usd("openai.gpt-oss-120b-1:0", MILLION) is None
    assert cost_usd("us.openai.gpt-oss-20b-1:0", MILLION) is None


def test_no_usage_means_no_cost_to_compute():
    assert cost_usd("us.anthropic.claude-sonnet-5", None) is None


def test_the_arithmetic_is_per_million_not_per_thousand():
    """The unit is the easiest thing to get wrong by three orders of
    magnitude, and a bill is where it would be noticed."""
    usage = TokenUsage(input_tokens=1000, output_tokens=500)

    # 1000 * 2.20/1M + 500 * 11.00/1M = 0.0022 + 0.0055
    assert cost_usd("us.anthropic.claude-sonnet-5", usage) == 0.0077


def test_case_and_padding_do_not_change_the_price():
    assert cost_usd("  US.Amazon.Nova-Lite-v1:0 ", MILLION) == 0.30


# --------------------------------------------------------------------------- #
# Bedrock addressing: routing prefixes and the regional premium.
# --------------------------------------------------------------------------- #


def test_the_bedrock_rate_is_the_regional_one():
    """Bedrock quotes a regional rate and a global one, and a `us.` inference
    profile, which is what this application uses, is billed at the regional
    one — 10 percent above the global number. Read off the rate cards, not
    remembered: 3.30/16.50 regional against 3.00/15.00 global."""
    assert cost_usd("anthropic.claude-sonnet-4-6", MILLION) == 19.80


def test_the_routing_prefix_does_not_change_the_price():
    """Bedrock addresses a model through an inference profile, so the id that
    was billed carries `us.` or `global.`. That decides which region serves the
    request, not what it costs."""
    for model in (
        "us.anthropic.claude-sonnet-4-6",
        "global.anthropic.claude-sonnet-4-6",
        "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ):
        assert cost_usd(model, MILLION) == 19.80


def test_a_bedrock_opus_is_not_priced_as_a_sonnet():
    assert cost_usd("us.anthropic.claude-opus-4-1", MILLION) == 99.0


def test_haiku_is_priced_from_its_own_rate_card():
    """1.10 and 5.50 per million in us-east-1, read with
    ListFoundationModelAgreementOffers."""
    assert cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", MILLION) == 6.60


def test_nova_is_the_cheap_tier_and_priced_as_such():
    """Nova Lite answers every fast-tier call, so its price is the one that
    decides what a forty-item plan costs."""
    assert cost_usd("us.amazon.nova-lite-v1:0", MILLION) == 0.30
    assert cost_usd("us.amazon.nova-pro-v1:0", MILLION) == 4.00
