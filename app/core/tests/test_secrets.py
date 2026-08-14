"""Unit tests for the startup secret audit.

The point of this check is narrow and worth stating: it is not validation, it
is a refusal. Every rule here exists because the value it rejects was, at some
point, actually sitting in a `.env` file in this repository.
"""

import pytest

from app.core.secrets import InsecureSecretError, audit_secrets, load_secrets

GOOD = "u7Qk2pR9vX4mZ8sT1bN6yH3wL5cJ0dF2"  # 32 characters


def env(**overrides: str) -> dict[str, str]:
    base = {
        "SECRET_KEY": GOOD,
        "JWT_ACCESS_SECRET": GOOD,
        "JWT_REFRESH_SECRET": GOOD[::-1],
        "POSTGRES_PASSWORD": GOOD,
        "MINIO_ROOT_PASSWORD": GOOD,
    }
    return {**base, **overrides}


class TestDevelopmentIsLeftAlone:
    """Nobody should have to generate 32-character secrets to run tests."""

    @pytest.mark.parametrize(
        "app_env", ["development", "test", "testing", "Development"]
    )
    def test_placeholders_are_fine_locally(self, app_env: str) -> None:
        problems = audit_secrets(env(POSTGRES_PASSWORD="change-me"), app_env=app_env)

        assert problems == []


class TestPlaceholders:
    """The exact value this repository was running on."""

    def test_change_me_is_refused(self) -> None:
        problems = audit_secrets(
            env(POSTGRES_PASSWORD="change-me"), app_env="production"
        )

        assert problems == ["POSTGRES_PASSWORD is still a placeholder"]

    @pytest.mark.parametrize(
        "value",
        [
            "change-me",
            "CHANGE_ME",
            "changeme",
            "change-me-in-production",
            "your-secret-here",
        ],
    )
    def test_a_placeholder_wearing_a_suffix_is_still_a_placeholder(
        self, value: str
    ) -> None:
        problems = audit_secrets(env(SECRET_KEY=value), app_env="production")

        assert problems == ["SECRET_KEY is still a placeholder"]


class TestWeakValues:
    def test_an_empty_secret_is_refused(self) -> None:
        assert audit_secrets(env(JWT_ACCESS_SECRET=""), app_env="production") == [
            "JWT_ACCESS_SECRET is empty"
        ]

    def test_a_short_secret_is_refused(self) -> None:
        problems = audit_secrets(env(SECRET_KEY="abc123"), app_env="production")

        assert "under the 32 minimum" in problems[0]

    def test_the_two_jwt_secrets_may_not_be_the_same(self) -> None:
        # Sharing them lets a stolen access token be replayed as a refresh
        # token, which is the one thing having two of them prevents.
        problems = audit_secrets(
            env(JWT_ACCESS_SECRET=GOOD, JWT_REFRESH_SECRET=GOOD), app_env="production"
        )

        assert problems == [
            "JWT_ACCESS_SECRET and JWT_REFRESH_SECRET are the same value"
        ]

    def test_debug_in_production_is_refused(self) -> None:
        assert audit_secrets(env(DEBUG="true"), app_env="production") == ["DEBUG is on"]


class TestReporting:
    def test_every_problem_is_reported_at_once(self) -> None:
        # One per deploy would cost a deploy per secret.
        problems = audit_secrets(
            env(
                SECRET_KEY="", POSTGRES_PASSWORD="change-me", JWT_ACCESS_SECRET="short"
            ),
            app_env="production",
        )

        assert len(problems) == 3

    def test_a_good_set_passes(self) -> None:
        assert audit_secrets(env(), app_env="production") == []


class TestProvider:
    def test_an_unknown_provider_fails_loudly(self) -> None:
        # A typo silently falling back to the file is how a production box
        # ends up running on whatever happened to be on disk.
        with pytest.raises(InsecureSecretError, match="unknown SECRETS_PROVIDER"):
            load_secrets(env(SECRETS_PROVIDER="vualt", APP_ENV="production"))

    def test_bad_secrets_stop_the_boot(self) -> None:
        with pytest.raises(InsecureSecretError, match="refusing to start"):
            load_secrets(env(POSTGRES_PASSWORD="change-me", APP_ENV="production"))

    def test_the_default_provider_is_the_environment(self) -> None:
        load_secrets(env(APP_ENV="production"))  # must not raise
