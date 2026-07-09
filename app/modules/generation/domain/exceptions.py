"""Generation domain exceptions."""

from fastapi import status

from app.shared.exceptions.base import AppError, NotFoundError


class GenerationNotFoundError(NotFoundError):
    """Raised when a generation run does not exist or is not owned by the user."""

    detail = "Generation run not found"


class PlannerError(AppError):
    """Raised when the planner agent cannot produce a valid roadmap."""

    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "The AI planner could not produce a valid plan roadmap"
