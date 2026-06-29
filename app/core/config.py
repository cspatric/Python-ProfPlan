"""Application settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    app_name: str = "ProfPlan"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Database / cache
    database_url: str
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_secret: str
    jwt_refresh_secret: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Auth cookies
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    access_cookie_name: str = "access_token"
    refresh_cookie_name: str = "refresh_token"

    # Login rate limiting (Redis)
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
