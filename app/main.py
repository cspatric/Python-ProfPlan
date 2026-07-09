"""Application entrypoint."""

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.exceptions import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.rate_limit import limiter
from app.api.router import api_router
from app.core.config import get_settings
from app.infrastructure.database.session import engine
from app.infrastructure.redis.client import redis_client
from app.infrastructure.telemetry.logging import setup_logging
from app.infrastructure.telemetry.traces import setup_tracing

settings = get_settings()

# Structured JSON logging to stdout (shipped to Loki by Promtail). Configure it
# before anything else so the whole process logs in one consistent format.
setup_logging(settings.log_level)

app = FastAPI(title="ProfPlan API")
register_exception_handlers(app)

# Per-IP rate limiting (slowapi + Redis). The global default limit is enforced by
# SlowAPIMiddleware on every route; a 429 is returned when a client floods the
# API. Added before the logging middleware so rejected requests are still logged.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# One structured log line per HTTP request (method, user, status, latency, ...).
app.add_middleware(RequestLoggingMiddleware)

# Prometheus metrics at /metrics (request rate, latency, status codes).
Instrumentator().instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)

# Distributed tracing (opt-in via OTEL_ENABLED).
if settings.otel_enabled:
    setup_tracing("profplan-api")
    FastAPIInstrumentor.instrument_app(app)

# CORS is only needed in development, where the React app (e.g. Vite on
# http://localhost:5173) and the API live on different origins. In production
# everything is served behind Traefik on a single origin, so no CORS is added.
if settings.is_development and settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
@limiter.exempt
def health() -> dict[str, str]:
    """Liveness probe (is the process up?) used by the container healthcheck."""
    return {"status": "ok"}


@app.get("/ready")
@limiter.exempt
async def ready(response: Response) -> dict[str, object]:
    """Readiness probe: verifies the database and Redis are reachable."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        healthy = False

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        healthy = False

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "degraded", "checks": checks}
