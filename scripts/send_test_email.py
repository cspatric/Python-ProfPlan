#!/usr/bin/env python
"""Send one email through whatever is configured, and say what happened.

    python scripts/send_test_email.py you@example.com

Exists because the first time a real mail server is configured, the failure is
almost never in the application: it is an app password with spaces in it, a
port that is blocked, or a sender the provider will not accept. Finding that
out from a password reset means the person who needed the email is the one who
discovers it is broken, and the error is two layers away in a Celery log.

This sends through the same adapter the application uses, so a message that
arrives here is a password reset that will arrive too.
"""

import argparse
import sys
from pathlib import Path

# Run from anywhere: python puts the *script's* directory on the path, not the
# one it was started from, so `python scripts/x.py` cannot see `app` without
# this. The documented command has to work as documented.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.infrastructure.email.sender import EmailMessage, get_email_sender


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipient", help="where to send it")
    args = parser.parse_args()

    settings = get_settings()
    server = f"{settings.smtp_host}:{settings.smtp_port}"
    print(f"enabled : {settings.email_enabled}")
    print(f"server  : {server} (tls={settings.smtp_use_tls})")
    print(f"login   : {settings.smtp_username or '(none)'}")
    print(f"from    : {settings.email_from_name} <{settings.email_from_address}>")
    print(f"to      : {args.recipient}")
    print()

    try:
        get_email_sender().send(
            EmailMessage(
                to=args.recipient,
                subject="ProfPlan test message",
                text=(
                    "If you are reading this, the mail configuration works and "
                    "password reset links will arrive the same way."
                ),
            )
        )
    except Exception as error:  # noqa: BLE001 — the whole point is to show it
        print(f"FAILED: {type(error).__name__}: {error}")
        return 1

    print("sent. If it does not arrive, check the spam folder before the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
