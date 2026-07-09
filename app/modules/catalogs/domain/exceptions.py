"""Catalog domain exceptions."""

from app.shared.exceptions.base import NotFoundError


class IconNotFoundError(NotFoundError):
    """Raised when an icon does not exist."""

    detail = "Icon not found"


class ColorNotFoundError(NotFoundError):
    """Raised when a color does not exist."""

    detail = "Color not found"
