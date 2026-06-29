"""Application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="ProfPlan API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe used by the container healthcheck."""
    return {"status": "ok"}
