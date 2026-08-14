#!/usr/bin/env python
"""Print a secret worth having.

    python scripts/new_secret.py            # one
    python scripts/new_secret.py --all      # every secret the audit requires

Exists so "generate a strong one" is a command rather than a suggestion. A
placeholder survives in a config file for exactly as long as replacing it is
more effort than leaving it.
"""

import argparse
import secrets

from app.core.secrets import REQUIRED_SECRETS

# 48 url-safe characters, comfortably past the 32 the audit demands.
LENGTH = 36


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="one per required secret")
    args = parser.parse_args()

    if not args.all:
        print(secrets.token_urlsafe(LENGTH))
        return

    for name in REQUIRED_SECRETS:
        print(f"{name}={secrets.token_urlsafe(LENGTH)}")


if __name__ == "__main__":
    main()
