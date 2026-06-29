"""Unit tests for password hashing and JWT helpers."""

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("Secret@123")
    assert hashed != "Secret@123"
    assert hashed.startswith("$argon2id$")
    assert verify_password("Secret@123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_verify_password_with_invalid_hash_returns_false() -> None:
    assert not verify_password("anything", "not-a-real-hash")


def test_access_token_roundtrip() -> None:
    token, _ = create_access_token("user-1")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"


def test_refresh_token_carries_session_id() -> None:
    token, _ = create_refresh_token("user-1", "session-1")
    payload = decode_refresh_token(token)
    assert payload["sub"] == "user-1"
    assert payload["sid"] == "session-1"
    assert payload["type"] == "refresh"


def test_access_decoder_rejects_a_refresh_token() -> None:
    refresh_token, _ = create_refresh_token("user-1", "session-1")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(refresh_token)


def test_refresh_decoder_rejects_an_access_token() -> None:
    access_token, _ = create_access_token("user-1")
    with pytest.raises(jwt.InvalidTokenError):
        decode_refresh_token(access_token)


def test_hash_token_is_deterministic_sha256() -> None:
    first = hash_token("a-token")
    second = hash_token("a-token")
    assert first == second
    assert len(first) == 64
    assert first != hash_token("another-token")
