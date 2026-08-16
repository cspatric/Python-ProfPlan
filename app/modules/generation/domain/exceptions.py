"""Generation domain exceptions."""

from fastapi import status

from app.shared.exceptions.base import AppError, NotFoundError


class GenerationNotFoundError(NotFoundError):
    """Raised when a generation run does not exist or is not owned by the user."""

    detail = "Generation run not found"


class BudgetExhaustedError(AppError):
    """Raised when an account has spent its monthly AI budget.

    402 rather than 429: this is not "too fast", it is "no more money this
    month", and a client that retries a 429 in a minute would be doing exactly
    the wrong thing. The message says when it resets, because an error that
    does not say what to do next is a support ticket.
    """

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    detail = "This account has used its AI budget for this month"


class PlannerError(AppError):
    """Raised when the planner agent cannot produce a valid roadmap."""

    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "The AI planner could not produce a valid plan roadmap"
