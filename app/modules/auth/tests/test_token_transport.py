"""Unit tests for how the access token is located on a request.

Both transports are accepted because the right one depends on the client (see
``_access_token``'s docstring). These tests pin the precedence so a future edit
cannot silently make an ambient cookie beat an explicit header.
"""

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.core.config import get_settings
from app.modules.auth.presentation.dependencies import _access_token

_COOKIE = get_settings().access_cookie_name


def _request(cookie: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"{_COOKIE}={cookie}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_bearer_header_is_used() -> None:
    assert _access_token(_request(), _bearer("from-header")) == (
        "from-header",
        "bearer",
    )


def test_cookie_is_used_when_there_is_no_header() -> None:
    assert _access_token(_request("from-cookie"), None) == ("from-cookie", "cookie")


def test_explicit_header_wins_over_ambient_cookie() -> None:
    assert _access_token(_request("from-cookie"), _bearer("from-header")) == (
        "from-header",
        "bearer",
    )


def test_no_credential_at_all() -> None:
    assert _access_token(_request(), None) is None


def test_empty_cookie_is_not_a_credential() -> None:
    assert _access_token(_request(""), None) is None
