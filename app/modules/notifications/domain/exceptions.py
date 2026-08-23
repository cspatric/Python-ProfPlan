"""Notification domain exceptions."""

from app.shared.exceptions.base import NotFoundError


class NotificationNotFoundError(NotFoundError):
    """Raised when a notification does not exist or is not the user's."""

    detail = "Notification not found"
