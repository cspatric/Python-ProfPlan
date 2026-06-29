"""Data transfer objects for the auth application layer."""

from dataclasses import dataclass
from datetime import datetime

from app.modules.users.infrastructure.models import User


@dataclass(slots=True)
class IssuedTokens:
    """Result of issuing a new pair of tokens."""

    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    user: User
