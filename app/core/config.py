"""Application settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import load_secrets


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

    # Sign in with Google. Empty client id disables the whole flow, including
    # the routes: an endpoint that exists and cannot work is worse than one
    # that is honestly absent.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Where Google sends the browser back. Must match the console exactly,
    # including the scheme and any trailing path.
    google_oauth_redirect_uri: str = (
        "http://localhost:5173/api/v1/auth/oauth/google/callback"
    )
    # Where the user lands afterwards, session cookies already set.
    oauth_success_redirect: str = "http://localhost:5173/subjects"
    oauth_failure_redirect: str = "http://localhost:5173/login"

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    # Runtime connections normally go through PgBouncer. Migrations and
    # anything needing session-level state must not: a pooler in transaction
    # mode can hand the next statement to a different backend. Empty means
    # "same as database_url", which is correct when there is no pooler.
    database_direct_url: str = ""
    # A read replica, for queries that tolerate replication lag. Empty means
    # there is no replica and every read stays on the primary — which is the
    # current deployment. Setting it is the whole of "add read capacity": the
    # second engine appears, the read dependency starts using it, and no
    # business code changes. Point it at the replica's own pooler.
    database_replica_url: str = ""
    # True when database_url points at PgBouncer in transaction mode. It
    # changes how asyncpg handles prepared statements; without it the app
    # fails intermittently under load, which is the worst way to find out.
    db_pgbouncer: bool = False

    # API-container DB connection budget, not a per-process pool size. The
    # number that has to stay under the server's limit is what one CONTAINER
    # presents, and a container holds one pool per uvicorn worker — so the
    # per-process pool is derived by dividing this budget by the worker count
    # (see app/infrastructure/database/session.py). Raising UVICORN_WORKERS
    # then costs nothing to reason about: the container's footprint is
    # unchanged, and scaling out is this one number times the replica count.
    db_client_conn_budget: int = 30
    # How many uvicorn workers this container runs. docker/api/start-api.sh
    # already reads UVICORN_WORKERS to launch them; this makes the same value
    # visible to the app, which is what lets the pool derive itself.
    uvicorn_workers: int = 1
    # Explicit per-process overrides. None means "derive from the budget",
    # which is the path that needs no maintenance; set them only to pin a
    # process to numbers the budget would not produce.
    db_pool_size: int | None = None
    db_max_overflow: int | None = None
    db_pool_timeout: int = 30

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

    # Login rate limiting (Redis) — checked both per-IP and per-account, so
    # neither a single attacker IP nor a distributed attack against one
    # account can brute-force past it.
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # CSRF (double-submit cookie). The access/refresh cookies are HttpOnly, so
    # a non-HttpOnly csrf_token cookie is mirrored into a request header by
    # the frontend; CSRFMiddleware compares the two on unsafe methods.
    csrf_protection_enabled: bool = True

    # Global per-IP rate limiting (slowapi + Redis) — protects every route from
    # request floods/DoS. Disabled in tests. Limits use the slowapi syntax
    # ("<count>/<period>", e.g. "120/minute"). ``default`` applies to all routes;
    # ``auth`` guards credential endpoints (brute force); ``expensive`` guards
    # AI/upload endpoints that consume real resources.
    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_expensive: str = "20/minute"
    rate_limit_storage_url: str = "redis://redis:6379/3"

    # Security headers. HSTS is only meaningful over HTTPS, so it defaults to
    # on in production and off in development. Everything else is always sent.
    security_headers_enabled: bool = True
    hsts_enabled: bool | None = None  # None -> follow the environment (prod only)

    # Uploads — reject anything larger before it can exhaust memory/disk.
    max_upload_size_mb: int = 100

    # Object storage (MinIO)
    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "profplan"
    minio_secure: bool = False

    # Embeddings (Ollama)
    ollama_base_url: str = "http://ollama:11434"
    # Measured on a CPU-only machine, per chunk of ~1200 characters:
    #   bge-m3            1.5s   1024-d   multilingual
    #   nomic-embed-text  0.9s    768-d   English-centric
    #   all-minilm        0.06s   384-d   English-centric, much weaker
    # bge-m3 is 24x slower than the fastest option and is kept anyway: the
    # material here is Portuguese, and the two faster models are trained for
    # English. A 2000-chunk book costs about 50 minutes to index once, against
    # retrieval quality on every plan generated afterwards.
    #
    # Switching this is NOT a settings change on its own: the vector size is
    # fixed by a migration (chunks.embedding) and every stored vector would
    # have to be recomputed. The ingestion refuses a mismatch rather than
    # discovering it on the insert.
    embedding_model: str = "bge-m3"
    # Chunks per embedding request. bge-m3 on a CPU costs about five seconds a
    # chunk and batching wins nothing, so this is sized so one request stays
    # far inside the timeout below, not to go faster.
    embedding_batch_size: int = 8
    # Characters per chunk. Fewer, larger chunks means less embedding time and
    # coarser retrieval; the trade is real in both directions, so it is a knob
    # rather than a constant. Only affects documents ingested from now on.
    embedding_chunk_chars: int = 1000
    # Per request, not per document. Eight chunks cost roughly forty seconds on
    # the slowest machine measured, so this leaves several times that in hand.
    embedding_timeout_seconds: float = 300.0

    # LLM gateway. Every remote model is reached through Amazon Bedrock; the
    # only other provider is the local Ollama, which is the floor of the
    # fallback chain. There is no direct-vendor integration on purpose: one
    # account, one bill, one credential, one quota.
    #
    # Amazon Bedrock, authenticated with a Bedrock API key rather than SigV4:
    # one bearer header, no boto3 and no credential chain. The model id must
    # be an *inference profile* (us. / global. prefix) for Anthropic's newer
    # models; the bare foundation-model id is not callable and says so with a
    # message that reads like a permissions error.
    bedrock_api_key: str = ""
    bedrock_region: str = "us-east-1"

    # One credential, three model families, and a larger and a smaller model in
    # each: the chain picks the family, the tier picks the size. A family whose
    # fast model is left empty answers everything with its one model.
    #
    # Anthropic. Leads the standard chain: the call that decides.
    bedrock_claude_model: str = "us.anthropic.claude-sonnet-5"
    bedrock_claude_fast_model: str = "us.anthropic.claude-haiku-4-5"
    # Amazon Nova. Leads the fast chain: cheapest per token of the three, and
    # bulk drafting against a decided roadmap is where the tokens are.
    bedrock_nova_model: str = "us.amazon.nova-pro-v1:0"
    bedrock_nova_fast_model: str = "us.amazon.nova-lite-v1:0"
    # OpenAI. What Bedrock serves of OpenAI is the *open-weight* gpt-oss
    # family, not the proprietary GPT-4o/5 line, which is not on Bedrock at
    # all. Confirm the exact id and that model access is granted for the
    # account before relying on it: a wrong id answers "not available for this
    # account", which reads like a permissions problem and is not one.
    bedrock_openai_model: str = "openai.gpt-oss-120b-1:0"
    bedrock_openai_fast_model: str = "openai.gpt-oss-20b-1:0"

    ollama_chat_model: str = "llama3.2:3b"

    # Figures on generated items. The item generator asks for an illustration by
    # describing it ({{figure: ...}}); this is where that description is turned
    # into a real, licensed image. Off by default in tests and CI, which have no
    # business reaching a public API.
    figures_enabled: bool = True
    commons_api_url: str = "https://commons.wikimedia.org/w/api.php"
    #: Wikimedia's policy requires an agent that identifies the application and
    #: gives a contact. A generic client is answered with 403, not with results.
    figure_user_agent: str = (
        "ProfPlan/1.0 (teaching-plan generator; +https://github.com/profplan)"
    )
    #: Commons renders the file at this width and hands back a PNG or JPEG, which
    #: is how an SVG diagram becomes something WeasyPrint can lay into a PDF.
    figure_thumbnail_width: int = 800
    figure_search_timeout_seconds: float = 15.0
    #: Candidates considered per description; the first usable one is taken.
    figure_search_limit: int = 5
    #: A week. The diagrams on Commons do not move, and the same description
    #: recurs across the items of one module.
    figure_cache_ttl_seconds: int = 604800
    ollama_fast_model: str = ""
    llm_max_tokens: int = 2048
    llm_timeout_seconds: float = 60.0
    # Auto-generate a plan with AI when it is created (planner + fan-out). When
    # false, POST /plans creates a plain plan with no AI call — used by CI and
    # any environment without an LLM configured.
    plan_generation_enabled: bool = True
    # Roadmap evaluation (generation/domain/roadmap_eval.py). Code checks are
    # free and always run; the LLM judge only runs when they flag something or
    # the retrieved context was weak, so a clean plan still costs one call.
    planner_eval_enabled: bool = True
    # Cosine distance (lower is closer) above which the closest retrieved chunk
    # is too far from the request to have grounded the plan — worth a judge.
    planner_weak_context_distance: float = 0.45

    # Hybrid retrieval: a word search alongside the vector one, fused by rank.
    # A switch rather than a rewrite, so the two can be compared on the same
    # corpus (scripts/eval_retrieval.py) instead of argued about.
    # What one account may spend on the AI in a calendar month, in USD at
    # list price. Zero turns the cap off. This is the only limit on money:
    # the rate limits cap requests per minute, which is a different thing,
    # and a request per minute on an expensive model is still a bill.
    llm_monthly_budget_usd: float = 5.0

    # Which model families answer which class of call, in order. Every name
    # here except ollama is a Bedrock family (see the model ids above).
    #
    # Two chains rather than one, because the cheap tier is not the same chain
    # with a smaller model: Claude leads the calls that decide and is absent
    # from the fast chain entirely, because forty drafting calls on a frontier
    # model is a bill dominated by the least difficult work. Nova leads the
    # bulk. OpenAI sits second in both as the family-level fallback, so a
    # single family being throttled does not drop the product to the local
    # model. Ollama is last in both: the floor, always.
    llm_standard_chain: str = "claude,openai,ollama"
    llm_fast_chain: str = "nova,openai,ollama"

    rag_hybrid_search: bool = True
    #: How many candidates each half contributes before fusion. Larger than the
    #: limit on purpose: fusion can only promote what one of the lists returned.
    rag_candidate_pool: int = 30
    #: The flattening constant in reciprocal rank fusion. 60 is the value from
    #: the original paper and it is not sensitive; it only has to be large
    #: enough that rank 1 does not swamp agreement between the lists.
    rag_rrf_k: int = 60
    llm_circuit_failure_threshold: int = 3
    llm_circuit_reset_seconds: float = 30.0
    # Caps concurrent outbound calls process-wide so a burst of /ai/ask
    # requests queues instead of firing unbounded concurrent HTTP chains.
    llm_max_concurrency: int = 5
    # Cache embeddings in Redis to avoid re-embedding identical text (7 days).
    embedding_cache_ttl_seconds: int = 604800
    # Keys per bulk Redis command. Redis runs commands on one thread, so an
    # unbounded MGET or a per-key write loop makes one big document everybody
    # else's latency problem. Bounding it means the cost of a command is a
    # constant of configuration instead of a function of what a user uploaded.
    redis_batch_size: int = 64

    # Email. Off by default: with EMAIL_ENABLED=false the message is written
    # to the log instead of sent, which is what development and CI want (the
    # link is the point, a mail server is not). Delivery always happens in a
    # Celery task, never in the request.
    #
    # The defaults describe the one transport this project uses, Resend over
    # submission TLS. They used to point at a local capture server on 1025,
    # which is no longer part of the stack — a default naming a host that does
    # not exist fails with a DNS error, and a DNS error reads as a network
    # problem rather than as missing configuration.
    email_enabled: bool = False
    smtp_host: str = "smtp.resend.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = 10.0
    email_from_address: str = "no-reply@profplan.local"
    email_from_name: str = "ProfPlan"
    # Where the links in those emails point. The token is consumed by the
    # frontend, which then calls the confirm endpoint.
    frontend_base_url: str = "http://localhost:5173"

    # Account lifecycle. Single-use tokens, stored only as a SHA-256 hash, the
    # same discipline as refresh tokens: a database leak must not hand over
    # the ability to reset somebody's password.
    password_reset_token_ttl_minutes: int = 30
    email_verification_token_ttl_hours: int = 48
    # When true, an unverified account cannot log in. Off by default so
    # existing accounts and dev environments keep working.
    require_email_verification: bool = False

    # Celery
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    # Broker queues whose depth is exported as a metric (comma separated).
    celery_queues: str = "celery"

    # Metrics probe — fills the dependency and queue-depth gauges that the
    # alert rules watch. Off under test, where there is nothing to probe.
    metrics_probe_enabled: bool = True
    metrics_probe_interval_seconds: float = 15.0

    # Tracing (OpenTelemetry). Opt-in; export goes to the OTel Collector.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"

    # Logging — structured JSON to stdout (shipped to Loki by Promtail).
    log_level: str = "INFO"

    @property
    def migration_url(self) -> str:
        """Where DDL and migrations connect: never through the pooler."""
        return self.database_direct_url or self.database_url

    @property
    def is_development(self) -> bool:
        """True when running in the development environment."""
        return self.app_env == "development"

    @property
    def cors_origins(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def hsts_active(self) -> bool:
        """Whether to send HSTS (explicit override, else production only)."""
        if self.hsts_enabled is not None:
            return self.hsts_enabled
        return not self.is_development

    @property
    def max_upload_size_bytes(self) -> int:
        """Upload size limit in bytes."""
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Secrets are pulled in first, from whatever `SECRETS_PROVIDER` points at,
    and refused if they would not survive contact with anyone. Doing it here
    rather than in `main.py` means the check runs for the workers and the
    migrations too, not only for the API.
    """
    load_secrets()
    return Settings()
