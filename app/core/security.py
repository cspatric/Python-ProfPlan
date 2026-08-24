"""Password hashing (Argon2id) and JWT helpers.

Argon2 is expensive on purpose, which makes it the one piece of CPU work in the
request path heavy enough to matter. Two rules keep it from becoming everybody
else's problem:

* **Never on the event loop.** The async wrappers below hand the work to a
  thread, so a login burst cannot stall unrelated requests. argon2-cffi releases
  the GIL, so threads genuinely parallelise here.
* **Bounded.** A semaphore sized from the container's own CPU grant caps how
  many hashes run at once. Past that, logins queue instead of starving the
  process, and the bound re-derives itself when the CPU limit changes — there is
  no number to retune when the deployment grows.

The synchronous functions stay: migrations, ``scripts/create_user.py`` and the
test fixtures call them from places where there is no event loop to protect.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.core.resources import cpu_bound_concurrency

_settings = get_settings()

# Argon2id is the default variant of argon2-cffi's PasswordHasher.
_password_hasher = PasswordHasher()

#: Concurrent Argon2 operations allowed in this process. Two per CPU: one lane
#: computing while another is scheduled keeps the cores busy without letting a
#: login flood queue unboundedly in the thread pool.
_HASH_CONCURRENCY = cpu_bound_concurrency(minimum=2, per_cpu=2)

_hash_slots: asyncio.Semaphore | None = None

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


def hash_concurrency() -> int:
    """The number of Argon2 operations this process runs at once."""
    return _HASH_CONCURRENCY


def _slots() -> asyncio.Semaphore:
    """The semaphore, created on first use inside the running loop.

    Built lazily rather than at import: this module is imported by the Celery
    worker and by scripts, where binding a semaphore to a loop that does not
    exist yet would fail.
    """
    global _hash_slots
    if _hash_slots is None:
        _hash_slots = asyncio.Semaphore(_HASH_CONCURRENCY)
    return _hash_slots


async def hash_password_async(password: str) -> str:
    """Hash a password off the event loop, bounded by the CPU grant."""
    async with _slots():
        return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """Verify a password off the event loop, bounded by the CPU grant."""
    async with _slots():
        return await asyncio.to_thread(verify_password, password, password_hash)


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
