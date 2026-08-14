"""The account-lifecycle emails.

Kept in the domain layer because the wording, and above all the security
statements in it ("if you did not ask for this"), are product decisions rather
than transport details. The sender knows nothing about these; it takes a
subject and a body.

Every message goes out as plain text *and* HTML. The text part is not a
fallback nobody reads: it is what a screen reader, a terminal client and a spam
filter see, and a message with only an HTML part scores worse in every filter
there is.

The HTML is written the way email HTML has to be written, which is 2005 and not
negotiable: tables for layout, every style inline, no external anything. Mail
clients strip `<style>` blocks, ignore flexbox and grid, and Outlook renders
through Word. Colours are hex because `oklch`, which is what the app's tokens
are written in, resolves to black in most clients; they are the same tokens
converted once, listed below.
"""

import html
from dataclasses import dataclass

#: The app's brand tokens (src/index.css) converted from oklch to hex.
BRAND = "#055cb2"
BRAND_DARK = "#004893"
CANVAS = "#eef2f7"
INK = "#1f2937"
MUTED = "#6b7280"
HAIRLINE = "#e5e7eb"

#: Blank characters after the preheader, so the client stops padding the inbox
#: line with whatever text happens to come next in the message.
_PREHEADER_PADDING = "&#8199;&#65279;&#847; " * 12


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """Subject plus both bodies, ready for the sending task."""

    subject: str
    text: str
    html: str


def _link(base_url: str, path: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?token={token}"


def _layout(
    *,
    preheader: str,
    heading: str,
    paragraphs: list[str],
    cta_label: str,
    cta_url: str,
    footnote: str,
) -> str:
    """The shell every one of these messages is poured into.

    One function rather than a template file: there are two emails, both are
    the same shape, and a template engine would be a dependency and a directory
    to hold two strings.

    Everything interpolated is escaped. Names come from the person's own
    profile, so this is not a script injection worth losing sleep over, but an
    apostrophe in a name should not break the markup either.
    """
    paragraph_style = f"margin:0 0 16px;font-size:15px;line-height:24px;color:{INK}"
    body = "".join(f'<p style="{paragraph_style}">{p}</p>' for p in paragraphs)
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{CANVAS};">
<!-- The line shown in the inbox next to the subject. Hidden in the message
     itself, which is why it is followed by enough blank characters to stop
     the client from padding it with whatever text comes next. -->
<div style="display:none;max-height:0;overflow:hidden;opacity:0">
{html.escape(preheader)}
{_PREHEADER_PADDING}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{CANVAS};padding:32px 12px">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="max-width:560px;width:100%">

        <tr>
          <td style="padding:0 4px 20px">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:{BRAND};border-radius:10px;width:36px;height:36px;
                           text-align:center;vertical-align:middle;font-family:
                           Helvetica,Arial,sans-serif;font-size:18px;font-weight:bold;
                           color:#ffffff;line-height:36px">P</td>
                <td style="padding-left:10px;font-family:Helvetica,Arial,sans-serif;
                           font-size:17px;font-weight:bold;color:{INK}">ProfPlan</td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="background:#ffffff;border-radius:16px;padding:32px;
                     font-family:Helvetica,Arial,sans-serif">
            <h1 style="margin:0 0 16px;font-size:20px;line-height:28px;color:{INK}">
              {html.escape(heading)}</h1>
            {body}

            <table role="presentation" cellpadding="0" cellspacing="0" border="0"
                   style="margin:24px 0 8px">
              <tr>
                <td style="background:{BRAND};border-radius:8px">
                  <a href="{html.escape(cta_url, quote=True)}"
                     style="display:inline-block;padding:13px 26px;font-size:15px;
                            font-weight:bold;color:#ffffff;text-decoration:none">
                    {html.escape(cta_label)}</a>
                </td>
              </tr>
            </table>

            <!-- The same link as text. A button is a link somebody cannot
                 copy, and clients that block styling leave nothing else. -->
            <p style="margin:16px 0 0;font-size:12px;line-height:20px;color:{MUTED}">
              If the button does not work, paste this into your browser:<br>
              <span style="color:{BRAND_DARK};word-break:break-all"
                >{html.escape(cta_url)}</span>
            </p>

            <p style="margin:24px 0 0;padding-top:20px;border-top:1px solid {HAIRLINE};
                      font-size:13px;line-height:21px;color:{MUTED}">{footnote}</p>
          </td>
        </tr>

        <tr>
          <td style="padding:20px 4px 0;font-family:Helvetica,Arial,sans-serif;
                     font-size:12px;line-height:20px;color:{MUTED};text-align:center">
            ProfPlan, teaching plans that write themselves.<br>
            This message was sent because someone used this address on ProfPlan.
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


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
    return RenderedEmail(
        "Reset your ProfPlan password",
        text,
        _layout(
            preheader=f"Choose a new password within {ttl_minutes} minutes.",
            heading="Choose a new password",
            paragraphs=[
                f"Hi {html.escape(name)},",
                "Someone asked to reset the password for your ProfPlan account. "
                f"The link below works for <strong>{ttl_minutes} minutes</strong> "
                "and can only be used once.",
            ],
            cta_label="Choose a new password",
            cta_url=url,
            footnote=(
                "If this was not you, you can ignore this message. Your password "
                "stays as it is, and nobody can change it without this link."
            ),
        ),
    )


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
    return RenderedEmail(
        "Confirm your ProfPlan address",
        text,
        _layout(
            preheader="Confirm your address to finish setting up ProfPlan.",
            heading="Confirm your address",
            paragraphs=[
                f"Hi {html.escape(name)},",
                "Confirm this address to finish setting up your ProfPlan account. "
                f"The link is valid for <strong>{ttl_hours} hours</strong>.",
            ],
            cta_label="Confirm my address",
            cta_url=url,
            footnote=(
                "If you did not create this account, you can ignore this message "
                "and nothing will happen."
            ),
        ),
    )
