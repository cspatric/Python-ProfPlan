"""Application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.exceptions import register_exception_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.infrastructure.telemetry.traces import setup_tracing

settings = get_settings()

app = FastAPI(title="ProfPlan API")
register_exception_handlers(app)

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
def health() -> dict[str, str]:
    """Liveness/readiness probe used by the container healthcheck."""
    return {"status": "ok"}
