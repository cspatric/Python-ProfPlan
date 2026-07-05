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

    # CORS — only used in development (production is same-origin via Traefik).
    # Comma-separated list of allowed origins.
    allowed_origins: str = "http://localhost:5173"

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

    # Object storage (MinIO)
    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "profplan"
    minio_secure: bool = False

    # Embeddings (Ollama)
    ollama_base_url: str = "http://ollama:11434"
    embedding_model: str = "bge-m3"

    # LLM gateway (fallback chain: Claude -> OpenAI -> Ollama)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    ollama_chat_model: str = "llama3.2:3b"
    llm_max_tokens: int = 2048
    llm_timeout_seconds: float = 60.0
    llm_circuit_failure_threshold: int = 3
    llm_circuit_reset_seconds: float = 30.0
    # Cache embeddings in Redis to avoid re-embedding identical text (7 days).
    embedding_cache_ttl_seconds: int = 604800

    # Celery
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Tracing (OpenTelemetry). Opt-in; export goes to the OTel Collector.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"

    # Logging — structured JSON to stdout (shipped to Loki by Promtail).
    log_level: str = "INFO"

    @property
    def is_development(self) -> bool:
        """True when running in the development environment."""
        return self.app_env == "development"

    @property
    def cors_origins(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
