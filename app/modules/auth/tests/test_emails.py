"""What the account emails must always contain.

The rendering is not tested pixel by pixel, mail clients would make that a lie
anyway. What is tested is the handful of things that make the difference
between an email that works and one that is quietly useless: the link is in
both bodies, the text body exists, and a name cannot break the markup.
"""

import pytest

from app.modules.auth.domain.emails import (
    email_verification_email,
    password_reset_email,
)

CASES = [
    lambda name: password_reset_email(
        name=name, base_url="https://profplan.app/", token="the-token", ttl_minutes=30
    ),
    lambda name: email_verification_email(
        name=name, base_url="https://profplan.app/", token="the-token", ttl_hours=48
    ),
]


@pytest.mark.parametrize("render", CASES)
def test_the_link_is_in_both_bodies(render):
    """The HTML part is what most people see and the text part is what the
    rest see, so a link in only one of them is a link half the readers do not
    have."""
    email = render("Teacher")

    assert "https://profplan.app/" in email.text
    assert "token=the-token" in email.text
    assert "token=the-token" in email.html


@pytest.mark.parametrize("render", CASES)
def test_the_link_is_also_readable_as_text_in_the_html(render):
    """A button is a link nobody can copy. Clients that strip styling, and
    people who forward the message, need the address itself."""
    email = render("Teacher")

    # Twice: once as the button's href, once printed for copying.
    assert email.html.count("token=the-token") >= 2


@pytest.mark.parametrize("render", CASES)
def test_a_name_cannot_break_the_markup(render):
    email = render('Ana "Nina" <script>alert(1)</script>')

    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html


@pytest.mark.parametrize("render", CASES)
def test_the_styles_are_inline_and_the_colours_are_hex(render):
    """Mail clients strip <style> blocks and do not understand oklch, which is
    what the app's own tokens are written in."""
    email = render("Teacher")

    assert "<style" not in email.html
    assert "oklch" not in email.html
    assert "#055cb2" in email.html


@pytest.mark.parametrize("render", CASES)
def test_nothing_is_loaded_from_outside(render):
    """No remote image, no font, no stylesheet: they are blocked by default,
    and the ones that are not are read receipts nobody asked for."""
    email = render("Teacher")

    assert "<img" not in email.html
    assert "<link" not in email.html
    assert "https://" in email.html  # the link itself, and nothing else
    assert email.html.count("https://") == email.html.count("https://profplan.app")
