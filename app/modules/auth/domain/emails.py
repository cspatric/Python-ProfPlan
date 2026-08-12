"""The account-lifecycle emails.

Kept in the domain layer because the wording, and above all the security
statements in it ("if you did not ask for this"), are product decisions rather
than transport details. The sender knows nothing about these; it takes a
subject and a body.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """Subject plus both bodies, ready for the sending task."""

    subject: str
    text: str
    html: str


def _link(base_url: str, path: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?token={token}"


def password_reset_email(
    *, name: str, base_url: str, token: str, ttl_minutes: int
) -> RenderedEmail:
    """Sent when someone asks to reset the password for an existing account."""
    url = _link(base_url, "reset-password", token)
    text = (
        f"Hi {name},\n\n"
        "Someone asked to reset the password for your ProfPlan account. "
        f"To choose a new one, open this link within {ttl_minutes} minutes:\n\n"
        f"{url}\n\n"
        "The link can only be used once.\n\n"
        "If this was not you, you can ignore this message. Your password stays "
        "as it is, and nobody can change it without this link.\n"
    )
    html = (
        f"<p>Hi {name},</p>"
        "<p>Someone asked to reset the password for your ProfPlan account. "
        f"To choose a new one, open this link within {ttl_minutes} minutes:</p>"
        f'<p><a href="{url}">Choose a new password</a></p>'
        "<p>The link can only be used once.</p>"
        "<p>If this was not you, you can ignore this message. Your password "
        "stays as it is, and nobody can change it without this link.</p>"
    )
    return RenderedEmail("Reset your ProfPlan password", text, html)


def email_verification_email(
    *, name: str, base_url: str, token: str, ttl_hours: int
) -> RenderedEmail:
    """Sent on registration, and again on request, to prove the address."""
    url = _link(base_url, "verify-email", token)
    text = (
        f"Hi {name},\n\n"
        "Confirm this address to finish setting up your ProfPlan account. "
        f"The link is valid for {ttl_hours} hours:\n\n"
        f"{url}\n\n"
        "If you did not create this account, you can ignore this message.\n"
    )
    html = (
        f"<p>Hi {name},</p>"
        "<p>Confirm this address to finish setting up your ProfPlan account. "
        f"The link is valid for {ttl_hours} hours:</p>"
        f'<p><a href="{url}">Confirm my address</a></p>'
        "<p>If you did not create this account, you can ignore this message.</p>"
    )
    return RenderedEmail("Confirm your ProfPlan address", text, html)
