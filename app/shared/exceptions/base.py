"""Base application exceptions mapped to HTTP responses.

Domain modules raise subclasses of these; the centralized exception handlers
(see app/api/exceptions.py) turn them into consistent JSON error responses, so
routers never map errors by hand.

Every error also carries a ``code``, and that is the part clients are meant to
read. ``detail`` is an English sentence for a developer looking at a response;
a sentence is not an API contract and cannot be translated by whoever displays
it. The code can: the interface is offered in three languages (see
``generation/domain/language.py`` for the same three) and it translates errors
by code, falling back to ``detail`` for a code it does not know yet.

The code is derived from the class name rather than written out on every class —
``AcademicItemNotFoundError`` becomes ``academic_item_not_found`` — because 19
domain errors that each need a hand-written constant are 19 chances to typo one,
and the typo is invisible until a person sees an untranslated message. A class
that wants a different code sets ``code`` explicitly and keeps it.
"""

import re

from fastapi import status

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _code_from(name: str) -> str:
    """``AcademicItemNotFoundError`` -> ``academic_item_not_found``."""
    return _CAMEL_BOUNDARY.sub("_", name.removesuffix("Error")).lower()


class AppError(Exception):
    """Base class for expected application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"
    #: Stable identifier for this failure, for clients that show their own text.
    code: str = "internal"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only when the subclass did not declare one of its own. Inheriting a
        # parent's code silently would give every NotFoundError the same
        # identifier, which is exactly the granularity a client cannot use.
        if "code" not in cls.__dict__:
            cls.code = _code_from(cls.__name__)

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    """The requested resource does not exist (or is not visible to the user)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class UnprocessableError(AppError):
    """The request is well-formed but references invalid data."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Unprocessable request"


class ConflictError(AppError):
    """The request conflicts with the current state."""

    status_code = status.HTTP_409_CONFLICT
    detail = "Conflict"


class UnauthorizedError(AppError):
    """Authentication is required or has failed."""

    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Not authenticated"


class ForbiddenError(AppError):
    """The authenticated user lacks permission for this action."""

    status_code = status.HTTP_403_FORBIDDEN
    detail = "Not allowed"


class RateLimitError(AppError):
    """Too many requests in the given window."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many requests"


class PayloadTooLargeError(AppError):
    """The request body exceeds the allowed size."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    detail = "Payload too large"


class UnsupportedMediaTypeError(AppError):
    """The uploaded content type is not accepted."""

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    detail = "Unsupported media type"
