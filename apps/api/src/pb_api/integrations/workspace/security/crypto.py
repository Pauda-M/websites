"""Credential encryption.

Secrets (client secrets, refresh tokens) are encrypted at rest with Fernet
(AES-128-CBC + HMAC authentication). Key rotation is first-class: the primary key
encrypts, and any number of retired keys can still decrypt, so a key can be rotated
without a flag-day re-encryption. When no key is configured an ephemeral key is
generated per process — acceptable for development only; production MUST supply a
persistent ``PB_WS_CREDENTIAL_ENCRYPTION_KEY``.
"""

from __future__ import annotations

import binascii

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CredentialCipher:
    """Authenticated symmetric encryption for stored credentials, with rotation."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("at least one Fernet key is required")
        self._fernet = MultiFernet([Fernet(_normalize_key(key)) for key in keys])

    @classmethod
    def from_key_material(
        cls, primary: str, *, retired: list[str] | None = None
    ) -> CredentialCipher:
        """Build a cipher, generating an ephemeral key if none is provided (dev only)."""
        if not primary:
            primary = Fernet.generate_key().decode("ascii")
        return cls([primary, *(retired or [])])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, binascii.Error, ValueError, TypeError) as exc:
            raise ValueError(
                "credential could not be decrypted (wrong key or corrupt token)"
            ) from exc

    def rotate(self, token: str) -> str:
        """Re-encrypt a token under the primary key (used during key rotation)."""
        return self._fernet.rotate(token.encode("ascii")).decode("ascii")


def _normalize_key(key: str) -> bytes:
    """Accept a urlsafe-base64 Fernet key as str; validate it is well-formed."""
    material = key.encode("ascii")
    Fernet(material)  # raises ValueError if malformed — fail fast on bad config
    return material


def generate_key() -> str:
    """Generate a new urlsafe-base64 Fernet key (for provisioning/rotation)."""
    return Fernet.generate_key().decode("ascii")
