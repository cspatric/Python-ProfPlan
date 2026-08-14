"""Where secrets come from, and what makes one unacceptable.

A `.env` file is fine on a laptop and wrong on a server. It puts the database
password, the JWT signing keys and three paid API keys in one plaintext file,
with no rotation, no audit and nothing stopping a placeholder from reaching
production. So the file stays for local work and production reads from a
secret store instead, chosen with `SECRETS_PROVIDER`.

The loader runs **before** `Settings` is built, and does the only thing that
lets a store be swapped without touching the rest of the app: it puts what it
fetched into the environment, where pydantic-settings already looks. Nothing
downstream knows or cares where a value came from.

The second half of this file is the part that earns its place. Fetching from a
store is plumbing; refusing to start with `POSTGRES_PASSWORD=change-me` outside
development is the check that would have caught the actual state of this
repository today.
"""

import logging
import os
import re

logger = logging.getLogger("app.secrets")

#: The variables that must never be a placeholder, a default, or empty outside
#: development. Not every secret in the file: these are the ones where a weak
#: value is an unauthenticated stranger rather than a broken feature.
REQUIRED_SECRETS = (
    "SECRET_KEY",
    "JWT_ACCESS_SECRET",
    "JWT_REFRESH_SECRET",
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_PASSWORD",
)

#: Values that are obviously not secrets. Matched case-insensitively anywhere
#: in the value, because "change-me-in-production" is the same mistake as
#: "change-me".
PLACEHOLDER_PATTERNS = (
    r"change[-_]?me",
    r"^changeme",
    r"^secret$",
    r"^password$",
    r"^test$",
    r"^dev$",
    r"^admin$",
    r"^your[-_]",
    r"^xxx+$",
    r"^placeholder",
)

#: Short enough to brute force. A signing key at 16 characters is a signing key
#: in name only.
MIN_SECRET_LENGTH = 32


class InsecureSecretError(RuntimeError):
    """Raised at startup when a secret would not survive contact with anyone."""


def _looks_like_a_placeholder(value: str) -> bool:
    return any(re.search(p, value, re.IGNORECASE) for p in PLACEHOLDER_PATTERNS)


def audit_secrets(env: dict[str, str], *, app_env: str) -> list[str]:
    """Return every reason the current secrets are unfit for `app_env`.

    Returns rather than raises so the caller can report all of them at once. A
    startup that fails on the first bad value costs a deploy per secret.
    """
    if app_env.lower() in ("development", "test", "testing"):
        return []

    problems: list[str] = []
    for name in REQUIRED_SECRETS:
        value = env.get(name, "")
        if not value:
            problems.append(f"{name} is empty")
        elif _looks_like_a_placeholder(value):
            problems.append(f"{name} is still a placeholder")
        elif len(value) < MIN_SECRET_LENGTH:
            problems.append(
                f"{name} is {len(value)} characters, "
                f"under the {MIN_SECRET_LENGTH} minimum"
            )

    if env.get("JWT_ACCESS_SECRET") and (
        env.get("JWT_ACCESS_SECRET") == env.get("JWT_REFRESH_SECRET")
    ):
        # Sharing them means a stolen access token can be replayed as a refresh
        # token, which is the one thing the pair of them exists to prevent.
        problems.append("JWT_ACCESS_SECRET and JWT_REFRESH_SECRET are the same value")

    if env.get("DEBUG", "").lower() in ("1", "true", "yes"):
        problems.append("DEBUG is on")

    return problems


def load_secrets(env: dict[str, str] | None = None) -> None:
    """Fetch secrets from the configured provider into the environment.

    Called once, before `Settings` is built. Unknown providers fail loudly:
    a typo in `SECRETS_PROVIDER` silently falling back to the file is how a
    production box ends up running on whatever happened to be on disk.
    """
    environment = os.environ if env is None else env
    provider = environment.get("SECRETS_PROVIDER", "env").strip().lower()

    if provider == "env":
        # The file, or whatever the orchestrator injected. Nothing to fetch.
        pass
    elif provider == "aws-ssm":
        _load_from_ssm(environment)
    else:
        raise InsecureSecretError(
            f"unknown SECRETS_PROVIDER '{provider}'; expected 'env' or 'aws-ssm'"
        )

    problems = audit_secrets(
        environment, app_env=environment.get("APP_ENV", "development")
    )
    if problems:
        raise InsecureSecretError(
            "refusing to start with these secrets:\n  "
            + "\n  ".join(problems)
            + "\n\nSee docs/deployment/SECRETS.md."
        )


def _load_from_ssm(env: dict[str, str]) -> None:
    """Read every parameter under a path in AWS SSM Parameter Store.

    Parameter Store rather than Secrets Manager: the values here are a handful
    of strings that rotate rarely, SecureString parameters are encrypted with
    KMS just the same, and Parameter Store is free at this size while Secrets
    Manager bills per secret per month.

    The parameter name after the prefix is the environment variable, so
    `/profplan/production/JWT_ACCESS_SECRET` becomes `JWT_ACCESS_SECRET` and
    adding a secret needs no code change.
    """
    import boto3  # imported here: only this provider needs the dependency

    prefix = env.get("SECRETS_PATH", "/profplan/production")
    client = boto3.client("ssm", region_name=env.get("AWS_REGION", "us-east-1"))

    paginator = client.get_paginator("get_parameters_by_path")
    found = 0
    for page in paginator.paginate(Path=prefix, Recursive=True, WithDecryption=True):
        for parameter in page["Parameters"]:
            name = parameter["Name"].rsplit("/", 1)[-1]
            # The environment wins on purpose: an operator overriding a value
            # for one boot must not be silently undone by the store.
            env.setdefault(name, parameter["Value"])
            found += 1

    if found == 0:
        raise InsecureSecretError(
            f"SECRETS_PROVIDER is aws-ssm but nothing was found under {prefix}"
        )
    logger.info("loaded %d secrets from SSM under %s", found, prefix)
