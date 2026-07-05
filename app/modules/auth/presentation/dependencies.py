"""FastAPI dependencies for the auth module."""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.infrastructure.database.session import get_session
from app.infrastructure.redis.client import get_redis
from app.modules.auth.application.service import AuthService
from app.modules.auth.infrastructure.rate_limit import LoginRateLimiter
from app.modules.auth.infrastructure.repository import (
    AuthLogRepository,
    RefreshTokenRepository,
)
from app.modules.users.domain.entities import UserRole
from app.modules.users.infrastructure.models import User
from app.modules.users.infrastructure.repository import UserRepository
from app.shared.exceptions.base import ForbiddenError

_settings = get_settings()


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AuthService:
    """Build an AuthService wired to the request-scoped session."""
    return AuthService(
        session=session,
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        auth_logs=AuthLogRepository(session),
        rate_limiter=LoginRateLimiter(redis),
    )


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the authenticated user from the access-token cookie."""
    token = request.cookies.get(_settings.access_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Expose the acting user to the request-logging middleware so every HTTP
    # log line records who performed the action.
    request.state.user_id = str(user.uuid)
    request.state.user_email = user.email
    request.state.user_role = user.role.value
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the authenticated user to have the admin role."""
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin privileges required")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
