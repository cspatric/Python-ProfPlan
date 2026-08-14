"""Unit tests for the printable handout.

The PDF itself is checked only for being a PDF; what these assert is the HTML
that goes into it, because that is where the content can silently go missing.
"""

import importlib.util
from datetime import date

import pytest

from app.modules.academic_items.application.handout_service import (
    HandoutContext,
    handout_filename,
    render_handout_html,
    render_handout_pdf,
)

_MARKDOWN = """## 1. Data set

| Employee | Days |
| :--- | :---: |
| Ana | 22 |

Let $x_{i,j}$ be the decision variable.

> **Note:** watch the rounding.

- first
- second
"""


def _context(**overrides: object) -> HandoutContext:
    base = {
        "title": "Logistics optimisation",
        "body": _MARKDOWN,
        "is_graded": False,
        "subject_name": "Applied Mathematics",
        "module_title": "Optimisation",
        "starts_at": date(2026, 8, 3),
        "ends_at": date(2026, 8, 3),
        "description": "A 50 minute group activity.",
    }
    return HandoutContext(**{**base, **overrides})  # type: ignore[arg-type]


def test_tables_become_real_tables() -> None:
    html = render_handout_html(_context())

    # The pipes must not survive as text: that is the bug this whole service
    # exists to fix.
    assert "<table>" in html
    assert "<th" in html and "Employee" in html
    assert "| Ana |" not in html


def test_inline_math_loses_its_dollars() -> None:
    html = render_handout_html(_context())

    assert '<span class="math">x_{i,j}</span>' in html
    assert "$x_{i,j}$" not in html


def test_currency_is_not_mistaken_for_math() -> None:
    html = render_handout_html(_context(body="The fare is R$ 5,00 per trip."))

    # "R$ 5,00 ... $" would otherwise be read as an expression and swallow the
    # text between two amounts.
    assert "R$ 5,00" in html
    assert '<span class="math">' not in html


def test_headings_lists_and_quotes_are_marked_up() -> None:
    html = render_handout_html(_context())

    assert "<h2>" in html
    assert "<ul>" in html and "<li>first</li>" in html
    assert "<blockquote>" in html


def test_cover_names_where_the_activity_sits() -> None:
    html = render_handout_html(_context())

    assert "Applied Mathematics" in html
    assert "Optimisation" in html
    assert "03 Aug 2026" in html
    assert "Activity" in html


def test_a_graded_item_is_labelled_an_evaluation() -> None:
    assert "Evaluation" in render_handout_html(_context(is_graded=True))


def test_a_period_shows_both_ends() -> None:
    html = render_handout_html(
        _context(starts_at=date(2026, 8, 3), ends_at=date(2026, 8, 7))
    )
    assert "03 Aug 2026 to 07 Aug 2026" in html


def test_title_is_escaped_not_injected() -> None:
    html = render_handout_html(_context(title="<script>alert(1)</script>"))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def _weasyprint_available() -> bool:
    if importlib.util.find_spec("weasyprint") is None:
        return False
    try:
        import weasyprint  # noqa: F401
    except OSError:
        # Installed, but its pango/cairo libraries are not on this machine.
        return False
    return True


@pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint's system libraries are absent here; the API image has them",
)
def test_render_produces_a_pdf() -> None:
    pdf = render_handout_pdf(_context())

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_filename_is_derived_from_the_title() -> None:
    assert (
        handout_filename("Atividade: Otimização (50 min)")
        == "atividade-otimiza-o-50-min.pdf"
    )
    assert handout_filename("///") == "activity.pdf"
