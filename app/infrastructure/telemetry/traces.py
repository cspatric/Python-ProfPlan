"""OpenTelemetry tracing setup and auto-instrumentation.

Opt-in via OTEL_ENABLED. Spans are exported (OTLP/gRPC) to the OTel Collector,
which forwards them to Tempo. Auto-instruments FastAPI (wired separately in
main.py), SQLAlchemy, Redis, httpx and Celery — so every request, DB query,
cache access, external call and background task is traced with no manual spans.
"""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings

logger = logging.getLogger("app.tracing")

_configured = False


def setup_tracing(service_name: str) -> None:
    """Configure the tracer provider and auto-instrument libraries.

    Safe to call multiple times and in both the API and worker processes;
    it is a no-op when OTEL_ENABLED is false or already configured.
    """
    global _configured
    settings = get_settings()
    if not settings.otel_enabled or _configured:
        return

    resource = Resource.create(
        {"service.name": service_name, "service.namespace": "profplan"}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint, insecure=True
            )
        )
    )
    trace.set_tracer_provider(provider)

    # Import the engine lazily to avoid a hard dependency at import time.
    from app.infrastructure.database.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    CeleryInstrumentor().instrument()

    _configured = True
    logger.info("OpenTelemetry tracing enabled for %s", service_name)
