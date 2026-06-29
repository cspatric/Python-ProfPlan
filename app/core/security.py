"""Password hashing (Argon2id) and JWT helpers."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_settings = get_settings()

# Argon2id is the default variant of argon2-cffi's PasswordHasher.
_password_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Return True when the stored hash should be upgraded."""
    return _password_hasher.check_needs_rehash(password_hash)


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _create_token(
    *,
    subject: str,
    token_type: str,
    secret: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Build a signed JWT, returning (token, jti, expires_at)."""
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, secret, algorithm=_settings.jwt_algorithm)
    return token, jti, expires_at


def create_access_token(subject: str) -> tuple[str, datetime]:
    """Create a short-lived access token."""
    token, _, expires_at = _create_token(
        subject=subject,
        token_type=ACCESS_TOKEN_TYPE,
        secret=_settings.jwt_access_secret,
        expires_delta=timedelta(minutes=_settings.access_token_expire_minutes),
    )
    return token, expires_at


def create_refresh_token(subject: str, session_id: str) -> tuple[str, datetime]:
    """Create a long-lived refresh token bound to a session id."""
    token, _, expires_at = _create_token(
        subject=subject,
        token_type=REFRESH_TOKEN_TYPE,
        secret=_settings.jwt_refresh_secret,
        expires_delta=timedelta(days=_settings.refresh_token_expire_days),
        extra_claims={"sid": session_id},
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token, raising on failure."""
    return _decode(token, _settings.jwt_access_secret, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token, raising on failure."""
    return _decode(token, _settings.jwt_refresh_secret, REFRESH_TOKEN_TYPE)


def _decode(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(token, secret, algorithms=[_settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def hash_token(token: str) -> str:
    """Return a SHA-256 hex digest used to store refresh tokens at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
