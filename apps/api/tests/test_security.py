from __future__ import annotations

import pytest

from pb_api.core.config import Settings
from pb_api.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from tests.conftest import build_test_settings


@pytest.fixture
def settings() -> Settings:
    return build_test_settings()


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("a-long-passphrase")
    assert hashed != "a-long-passphrase"
    assert verify_password("a-long-passphrase", hashed)
    assert not verify_password("a-different-passphrase", hashed)


def test_hashes_are_salted() -> None:
    assert hash_password("same-password-xyz") != hash_password("same-password-xyz")


def test_access_token_roundtrip(settings: Settings) -> None:
    token = create_access_token(subject="user-1", role="client", settings=settings)
    claims = decode_token(token, expected_type="access", settings=settings)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "client"
    assert claims["type"] == "access"
    assert claims["jti"]


def test_refresh_token_type_enforced(settings: Settings) -> None:
    token = create_refresh_token(subject="user-1", settings=settings)
    with pytest.raises(TokenError, match="expected"):
        decode_token(token, expected_type="access", settings=settings)


def test_token_signature_verified(settings: Settings) -> None:
    other = build_test_settings(secret_key="a-completely-different-signing-key-123456")
    token = create_access_token(subject="user-1", role="client", settings=settings)
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access", settings=other)


def test_tampered_token_rejected(settings: Settings) -> None:
    token = create_access_token(subject="user-1", role="client", settings=settings)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(TokenError):
        decode_token(tampered, expected_type="access", settings=settings)
