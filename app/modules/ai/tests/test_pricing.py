"""The price table, and the two answers it must keep apart.

`None` means "nobody priced this model" and `0.0` means "this model is free".
Collapsing them is the failure this file exists to prevent: an unpriced model
counted as free makes a cost report that is quietly missing the expensive half.
"""

from app.modules.ai.domain.pricing import cost_usd
from app.modules.ai.domain.usage import TokenUsage

MILLION = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)


def test_a_priced_model_costs_what_the_table_says():
    # claude-sonnet is 3.00 in and 15.00 out per million.
    assert cost_usd("claude-sonnet-5", MILLION) == 18.0


def test_the_dated_variant_is_priced_like_its_family():
    """Providers append a date to the model that answered, and the price does
    not change with it."""
    assert cost_usd("claude-sonnet-5-20260114", MILLION) == 18.0


def test_the_longest_prefix_wins():
    """gpt-4o-mini must not be billed as gpt-4o, which is 16 times the price."""
    assert cost_usd("gpt-4o-mini", MILLION) == 0.75
    assert cost_usd("gpt-4o", MILLION) == 12.50


def test_a_local_model_is_free_rather_than_unknown():
    assert cost_usd("llama3.2:3b", MILLION) == 0.0


def test_an_unknown_model_has_no_price_at_all():
    """Not zero. Zero would be a lie that balances the books."""
    assert cost_usd("some-new-model-nobody-priced", MILLION) is None


def test_no_usage_means_no_cost_to_compute():
    assert cost_usd("claude-sonnet-5", None) is None


def test_the_arithmetic_is_per_million_not_per_thousand():
    """The unit is the easiest thing to get wrong by three orders of
    magnitude, and a bill is where it would be noticed."""
    usage = TokenUsage(input_tokens=1000, output_tokens=500)

    # 1000 * 3/1M + 500 * 15/1M = 0.003 + 0.0075
    assert cost_usd("claude-sonnet-5", usage) == 0.0105


def test_case_and_padding_do_not_change_the_price():
    assert cost_usd("  GPT-4o-Mini ", MILLION) == 0.75


# --------------------------------------------------------------------------- #
# Bedrock ids, which are the same models under different names.
# --------------------------------------------------------------------------- #


def test_a_bedrock_model_costs_10_percent_more_than_the_direct_one():
    """Bedrock quotes a regional rate and a global one, and a `us.` inference
    profile, which is what this application uses, is billed at the regional
    one. Read off the rate cards, not remembered."""
    assert cost_usd("claude-sonnet-4-6", MILLION) == 18.0
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


def test_sonnet_5_is_not_priced_like_the_4_x_family():
    """From the rate card on the model's own Bedrock agreement offer, not from
    memory: 2.20 in and 11.00 out per million, against 3 and 15 for 4.x."""
    assert cost_usd("us.anthropic.claude-sonnet-5", MILLION) == 13.20
    assert cost_usd("anthropic.claude-sonnet-4-6", MILLION) == 19.80
