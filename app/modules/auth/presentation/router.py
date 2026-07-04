"""Authentication HTTP endpoints."""

from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.modules.auth.application.dto import IssuedTokens
from app.modules.auth.presentation.dependencies import (
    AuthServiceDep,
    CurrentUser,
)
from app.modules.auth.presentation.schemas import (
    LoginRequest,
    MessageResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _set_auth_cookies(response: Response, tokens: IssuedTokens) -> None:
    response.set_cookie(
        key=_settings.access_cookie_name,
        value=tokens.access_token,
        max_age=_settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=_settings.cookie_secure,
        samesite=_settings.cookie_samesite,
        domain=_settings.cookie_domain,
        path="/",
    )
    response.set_cookie(
        key=_settings.refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=_settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=_settings.cookie_secure,
        samesite=_settings.cookie_samesite,
        domain=_settings.cookie_domain,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in (_settings.access_cookie_name, _settings.refresh_cookie_name):
        response.delete_cookie(key=name, domain=_settings.cookie_domain, path="/")


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> UserResponse:
    """Authenticate with email/password and set the auth cookies.

    Invalid credentials (401) and rate limiting (429) are raised by the service
    and turned into responses by the central exception handlers.
    """
    tokens = await service.login(
        email=payload.email,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, tokens)
    return UserResponse.model_validate(tokens.user)


@router.post("/refresh", response_model=UserResponse)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> UserResponse:
    """Rotate the refresh token and re-issue the auth cookies.

    Invalid/expired tokens and reuse detection (401) are raised by the service
    and handled centrally.
    """
    tokens = await service.refresh(
        raw_token=request.cookies.get(_settings.refresh_cookie_name),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, tokens)
    return UserResponse.model_validate(tokens.user)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> MessageResponse:
    """Revoke the current session and clear cookies."""
    await service.logout(
        raw_token=request.cookies.get(_settings.refresh_cookie_name),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _clear_auth_cookies(response)
    return MessageResponse(detail="Logged out")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    user: CurrentUser,
) -> MessageResponse:
    """Revoke every session of the authenticated user."""
    revoked = await service.logout_all(
        user_id=user.uuid,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _clear_auth_cookies(response)
    return MessageResponse(detail=f"Revoked {revoked} session(s)")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(user)
