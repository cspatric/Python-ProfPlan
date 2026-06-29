"""User domain entities and value objects."""

from enum import StrEnum


class UserStatus(StrEnum):
    """Lifecycle status of a user account."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
