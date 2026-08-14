"""Talking to Google's OAuth endpoints.

The authorization code flow for a confidential client: the browser is sent to
Google, comes back with a one-time code, and the **server** exchanges that code
for tokens over its own TLS connection. The client secret never leaves this
process and no token ever passes through the browser.

Two details carry most of the security here.

**The `state` is stored server side, in Redis, and is single use.** A state
that is only echoed back proves nothing; one that has to be found in a store
and is deleted on use is what makes a forged callback fail. It expires, because
an authorization that has been sitting around for an hour is not one anybody is
waiting on.

**The ID token's signature is not verified, and that is deliberate.** It did
not come from the browser: it came back on this process's own TLS connection to
`oauth2.googleapis.com`, authenticated with the client secret. The channel is
the proof. What still has to be checked is what the token *claims*, because a
token that is genuine and meant for a different application is worth nothing
here, so `aud`, `iss` and `exp` are all verified below.
"""

import base64
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.modules.auth.domain.exceptions import InvalidTokenError

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

#: Long enough to sign in on a slow connection, short enough that an abandoned
#: attempt is not still usable when someone finds the link in a history file.
STATE_TTL_SECONDS = 600

_STATE_PREFIX = "oauth:state:"

#: Everything this needs and nothing else: who the person is, and an address to
#: recognise them by. No Drive, no calendar, no offline access.
SCOPES = ("openid", "email", "profile")


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """The parts of Google's answer this application acts on."""

    subject: str
    email: str
    email_verified: bool
    name: str


async def start(redis: Redis) -> str:
    """Return the URL to send the browser to, remembering the state."""
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    await redis.setex(f"{_STATE_PREFIX}{state}", STATE_TTL_SECONDS, "1")

    query = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            # Google only returns an email on the first consent unless asked;
            # this keeps a second sign-in from arriving without one.
            "prompt": "select_account",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def consume_state(redis: Redis, state: str | None) -> None:
    """Check the callback belongs to a flow this server started. Single use."""
    if not state:
        raise InvalidTokenError
    # DELETE returns how many keys it removed, so finding and consuming the
    # state is one atomic step: two callbacks racing cannot both succeed.
    if await redis.delete(f"{_STATE_PREFIX}{state}") != 1:
        raise InvalidTokenError


async def exchange(code: str) -> GoogleIdentity:
    """Trade the one-time code for the identity behind it."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code != 200:
        raise InvalidTokenError

    id_token = response.json().get("id_token")
    if not id_token:
        raise InvalidTokenError

    return _read_id_token(id_token)


def _read_id_token(id_token: str) -> GoogleIdentity:
    """Decode the claims and check the ones that matter.

    See the module docstring for why the signature is not checked and these
    are.
    """
    settings = get_settings()
    try:
        payload_segment = id_token.split(".")[1]
        # JWT segments are base64url without padding; add the maximum, which
        # the decoder ignores when it is not needed.
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + "=="))
    except (IndexError, ValueError) as exc:
        raise InvalidTokenError from exc

    if payload.get("aud") != settings.google_oauth_client_id:
        # Genuine, and meant for somebody else's application.
        raise InvalidTokenError
    if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise InvalidTokenError
    if float(payload.get("exp", 0)) < time.time():
        raise InvalidTokenError

    subject = payload.get("sub")
    email = payload.get("email")
    if not subject or not email:
        raise InvalidTokenError

    return GoogleIdentity(
        subject=subject,
        email=email.strip().lower(),
        email_verified=bool(payload.get("email_verified")),
        name=payload.get("name") or email.split("@")[0],
    )
