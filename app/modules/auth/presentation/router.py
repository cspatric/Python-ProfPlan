"""Authentication HTTP endpoints."""

import logging
import secrets

from fastapi import APIRouter, Request, Response, status

from app.api.csrf import CSRF_COOKIE_NAME
from app.api.rate_limit import auth_limit
from app.core.config import get_settings
from app.modules.auth.application.dto import IssuedTokens
from app.modules.auth.presentation.dependencies import (
    AccountServiceDep,
    AuthServiceDep,
    CurrentUser,
)
from app.modules.auth.presentation.schemas import (
    EmailVerificationConfirm,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    UserResponse,
)

logger = logging.getLogger("app.auth")
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
    # Not HttpOnly on purpose: the frontend must read it and mirror it into
    # the X-CSRF-Token header (see app/api/csrf.py).
    #
    # It lives as long as the refresh cookie, not as long as the access one.
    # The value carries no authority: it only has to be unreadable from
    # another origin. Expiring it with the access token instead left the
    # browser holding a refresh cookie and no CSRF cookie, which the
    # middleware answers with 403 on every write, including the POST to
    # /auth/refresh that would have fixed it. The session became unusable
    # fifteen minutes in, with no way out but logging in again.
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=_settings.refresh_token_expire_days * 86400,
        httponly=False,
        secure=_settings.cookie_secure,
        samesite=_settings.cookie_samesite,
        domain=_settings.cookie_domain,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in (
        _settings.access_cookie_name,
        _settings.refresh_cookie_name,
        CSRF_COOKIE_NAME,
    ):
        response.delete_cookie(key=name, domain=_settings.cookie_domain, path="/")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
@auth_limit
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    accounts: AccountServiceDep,
) -> UserResponse:
    """Create a new account and sign in (sets the auth cookies).

    A duplicate email raises 409, handled by the central exception handlers.
    """
    tokens = await service.register(
        name=payload.name,
        email=payload.email,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # Prove the address, but do not block on it: the account works right away
    # unless REQUIRE_EMAIL_VERIFICATION says otherwise. The email is queued,
    # so a slow mail server cannot make registration slow or fail.
    #
    # And if queueing itself fails (broker down), the registration still
    # succeeded: the account exists and the user is signed in. Turning that
    # into a 500 would tell them their sign-up failed when it did not, and
    # they can ask for a new link from the app.
    try:
        await accounts.send_email_verification(
            user=tokens.user, ip_address=_client_ip(request)
        )
    except Exception:  # noqa: BLE001 — never fail a good registration
        logger.exception("could not queue the verification email")
    _set_auth_cookies(response, tokens)
    return UserResponse.model_validate(tokens.user)


@router.post("/login", response_model=UserResponse)
@auth_limit
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


@router.post(
    "/password-reset",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@auth_limit
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    service: AccountServiceDep,
) -> MessageResponse:
    """Send a password reset link to the address, if it has an account.

    Always 202, and always the same body. Answering 404 for an unknown address
    would turn this endpoint into a way to ask "does this person have an
    account here", which is the first thing a credential-stuffing run wants.
    Rate limited like the other credential endpoints.
    """
    await service.request_password_reset(
        email=payload.email,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(
        detail="If that address has an account, a reset link is on its way."
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
@auth_limit
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    service: AccountServiceDep,
) -> MessageResponse:
    """Set a new password using a reset token, and end every session.

    Every session is revoked on purpose: a reset is often the response to
    someone else having the account, and leaving their session alive would
    give it straight back. The user signs in again with the new password.
    """
    await service.confirm_password_reset(
        token=payload.token,
        new_password=payload.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(detail="Password updated. Sign in again.")


@router.post(
    "/email-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@auth_limit
async def resend_email_verification(
    request: Request,
    response: Response,
    user: CurrentUser,
    service: AccountServiceDep,
) -> MessageResponse:
    """Send a fresh verification link to the signed-in user's address.

    A no-op for an address that is already verified, and the answer does not
    say which case it was.
    """
    await service.send_email_verification(user=user, ip_address=_client_ip(request))
    return MessageResponse(
        detail="If the address needs confirming, a link is on its way."
    )


@router.post("/email-verification/confirm", response_model=UserResponse)
@auth_limit
async def confirm_email_verification(
    payload: EmailVerificationConfirm,
    request: Request,
    response: Response,
    service: AccountServiceDep,
) -> UserResponse:
    """Prove ownership of the address with a verification token."""
    user = await service.confirm_email_verification(
        token=payload.token,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return UserResponse.model_validate(user)
