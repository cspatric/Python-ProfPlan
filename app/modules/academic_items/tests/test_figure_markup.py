"""The generator's figure placeholder: what is extracted, and what is left."""

from app.modules.generation.domain import figure_markup


def test_a_placeholder_is_extracted() -> None:
    markdown = "Read this.\n\n{{figure: labelled diagram of a neuron}}\n\nThen that."

    assert figure_markup.extract_queries(markdown) == ["labelled diagram of a neuron"]


def test_whitespace_and_case_in_the_directive_are_tolerated() -> None:
    assert figure_markup.extract_queries("{{ FIGURE :  the\n  Krebs cycle }}") == [
        "the Krebs cycle"
    ]


def test_the_same_description_twice_is_one_lookup() -> None:
    """Two placeholders asking for the same thing is one image used twice."""
    markdown = "{{figure: a neuron}}\n\ntext\n\n{{figure: a neuron}}"

    assert figure_markup.extract_queries(markdown) == ["a neuron"]


def test_a_model_that_asks_for_eight_figures_gets_three() -> None:
    markdown = "\n".join(f"{{{{figure: diagram {i}}}}}" for i in range(8))

    assert len(figure_markup.extract_queries(markdown)) == 3


def test_no_placeholders_is_not_an_error() -> None:
    assert figure_markup.extract_queries("just prose") == []


def test_resolved_placeholders_are_replaced() -> None:
    markdown = "Before\n\n{{figure: a neuron}}\n\nAfter"

    result = figure_markup.replace(markdown, {"a neuron": "![alt](path.png)"})

    assert "![alt](path.png)" in result
    assert "{{figure" not in result


def test_an_unresolved_placeholder_is_removed_not_left_behind() -> None:
    """A student must never see the directive. One fewer figure is fine."""
    markdown = "Before\n\n{{figure: something nobody drew}}\n\nAfter"

    result = figure_markup.replace(markdown, {})

    assert "{{figure" not in result
    assert "Before" in result and "After" in result
    # And no hole where it was.
    assert "\n\n\n" not in result
