"""Unit tests for the admin authorization dependency."""

from uuid import uuid4

import pytest

from app.modules.auth.presentation.dependencies import get_current_admin
from app.modules.users.domain.entities import UserRole
from app.modules.users.infrastructure.models import User
from app.shared.exceptions.base import ForbiddenError


def _user(role: UserRole) -> User:
    return User(
        uuid=uuid4(),
        name="X",
        email="x@x.com",
        password_hash="h",
        role=role,
    )


async def test_admin_is_allowed() -> None:
    admin = _user(UserRole.ADMIN)
    assert await get_current_admin(admin) is admin


async def test_regular_user_is_forbidden() -> None:
    with pytest.raises(ForbiddenError):
        await get_current_admin(_user(UserRole.USER))
