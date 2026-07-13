"""Password hashing and JWT issuing/verification.

Passwords are hashed with Argon2id (pwdlib recommended profile). Tokens are
short-lived HS256 JWTs: access tokens additionally carry the user's role for
RBAC checks. Every token (access and refresh) carries a ``jti`` and issuer, so
a revocation store can be added without a token-format change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from pb_api.core.config import Settings

TokenType = Literal["access", "refresh"]

_password_hasher = PasswordHash.recommended()


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or of the wrong type."""


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hasher.verify(password, hashed)


def dummy_verify() -> None:
    """Burn hashing time for unknown users to blunt timing-based user enumeration."""
    _password_hasher.verify("invalid-password", _DUMMY_HASH)


_DUMMY_HASH = _password_hasher.hash("dummy-password-for-timing")


def _create_token(
    *,
    subject: str,
    token_type: TokenType,
    settings: Settings,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
        "iss": settings.app_name,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, settings.secret_key.get_secret_value(), settings.jwt_algorithm)


def create_access_token(*, subject: str, role: str, settings: Settings) -> str:
    return _create_token(
        subject=subject,
        token_type="access",  # noqa: S106 - token kind discriminator, not a credential
        settings=settings,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={"role": role},
    )


def create_refresh_token(*, subject: str, settings: Settings) -> str:
    return _create_token(
        subject=subject,
        token_type="refresh",  # noqa: S106 - token kind discriminator, not a credential
        settings=settings,
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
    )


def decode_token(token: str, *, expected_type: TokenType, settings: Settings) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return claims
