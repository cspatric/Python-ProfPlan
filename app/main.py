"""Application entrypoint."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="ProfPlan API")
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe used by the container healthcheck."""
    return {"status": "ok"}
