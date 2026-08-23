"""Which figures this system is allowed to reuse, and which bytes it trusts.

A figure is not decoration — a student reads facts off it — so the licence and
the file signature are both checks rather than metadata.
"""

import pytest

from app.modules.academic_items.domain.exceptions import UnusableFigureError
from app.modules.academic_items.domain.figures import (
    FigureCandidate,
    FigureSource,
    is_licence_allowed,
    is_usable,
    suffix_for,
    validate_image_bytes,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff" + b"0" * 64


def _candidate(**overrides) -> FigureCandidate:
    defaults = {
        "source": FigureSource.WIKIMEDIA,
        "source_url": "https://commons.wikimedia.org/wiki/File:Neuron.png",
        "image_url": "https://upload.wikimedia.org/thumb/Neuron.png",
        "title": "Neuron.png",
        "mime_type": "image/png",
        "width": 800,
        "height": 600,
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Jane Doe",
    }
    return FigureCandidate(**{**defaults, **overrides})


@pytest.mark.parametrize(
    "licence",
    ["CC0", "CC BY 4.0", "CC BY-SA 3.0", "Public domain", "PD-USGov", "cc-by-2.0"],
)
def test_free_licences_are_allowed(licence: str) -> None:
    assert is_licence_allowed(licence)


@pytest.mark.parametrize(
    "licence",
    ["CC BY-NC 4.0", "CC BY-ND 4.0", "CC BY-NC-SA 3.0", "All rights reserved"],
)
def test_restrictive_licences_are_refused(licence: str) -> None:
    """NC forbids the commercial use a paid product is; ND forbids laying the
    figure into a handout at all."""
    assert not is_licence_allowed(licence)


def test_an_unknown_licence_is_not_assumed_to_be_free() -> None:
    assert not is_licence_allowed(None)
    assert not is_licence_allowed("")


def test_a_usable_candidate() -> None:
    assert is_usable(_candidate())


def test_an_icon_sized_result_is_not_a_diagram() -> None:
    assert not is_usable(_candidate(width=64, height=64))


def test_a_type_that_will_not_render_in_the_pdf_is_refused() -> None:
    """SVG renders on screen and not reliably in WeasyPrint, so it is not
    offered at all rather than offered and then missing from the handout."""
    assert not is_usable(_candidate(mime_type="image/svg+xml"))


def test_the_credit_line_names_someone() -> None:
    assert _candidate().credit == "Jane Doe — CC BY-SA 4.0"
    assert _candidate(attribution=None).credit == "Wikimedia Commons — CC BY-SA 4.0"


def test_real_image_bytes_pass() -> None:
    validate_image_bytes(PNG, mime_type="image/png")
    validate_image_bytes(JPEG, mime_type="image/jpeg")


def test_a_declared_type_that_the_bytes_contradict_is_rejected() -> None:
    """The declared type is what a remote server said; the magic bytes are what
    it actually sent. Same rule an upload lives under."""
    with pytest.raises(UnusableFigureError, match="does not match"):
        validate_image_bytes(b"<html>not an image</html>", mime_type="image/png")


def test_an_empty_body_is_rejected() -> None:
    with pytest.raises(UnusableFigureError, match="empty"):
        validate_image_bytes(b"", mime_type="image/png")


def test_an_oversized_image_is_rejected() -> None:
    with pytest.raises(UnusableFigureError, match="larger than"):
        validate_image_bytes(PNG + b"0" * (6 * 1024 * 1024), mime_type="image/png")


def test_the_stored_suffix_follows_the_type() -> None:
    assert suffix_for("image/png") == ".png"
    assert suffix_for("image/jpeg") == ".jpg"
