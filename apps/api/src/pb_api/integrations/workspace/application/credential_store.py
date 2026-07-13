"""Encrypted credential store — implements the ``CredentialStore`` port.

Secrets (client secret, refresh token) are encrypted with the Fernet cipher before
they touch the database and decrypted only in memory when a token must be minted.
Refresh-token rotation persists the new (encrypted) token. Every credential access
is audited. Nothing here logs or returns a plaintext secret.
"""

from __future__ import annotations

import uuid

from pb_api.integrations.workspace.infrastructure.repositories import CredentialRepository
from pb_api.integrations.workspace.ports.credentials import OAuthGrant
from pb_api.integrations.workspace.security.audit import AuditLog
from pb_api.integrations.workspace.security.crypto import CredentialCipher


class EncryptedCredentialStore:
    """A ``CredentialStore`` that keeps secrets encrypted at rest."""

    def __init__(
        self, repository: CredentialRepository, cipher: CredentialCipher, audit: AuditLog
    ) -> None:
        self._repo = repository
        self._cipher = cipher
        self._audit = audit

    async def save(self, grant: OAuthGrant) -> None:
        await self._repo.upsert(
            grant.tenant_id,
            grant.connection_id,
            provider_tenant_id=grant.provider_tenant_id,
            client_id=grant.client_id,
            client_secret_encrypted=self._cipher.encrypt(grant.client_secret),
            refresh_token_encrypted=(
                self._cipher.encrypt(grant.refresh_token) if grant.refresh_token else None
            ),
            scopes=grant.scopes,
        )
        await self._audit.emit(
            grant.tenant_id,
            "credential.save",
            resource=str(grant.connection_id),
        )

    async def load(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> OAuthGrant | None:
        row = await self._repo.get(tenant_id, connection_id)
        if row is None:
            return None
        await self._audit.emit(tenant_id, "credential.load", resource=str(connection_id))
        return OAuthGrant(
            tenant_id=tenant_id,
            connection_id=connection_id,
            provider_tenant_id=row.provider_tenant_id,
            client_id=row.client_id,
            client_secret=self._cipher.decrypt(row.client_secret_encrypted),
            refresh_token=(
                self._cipher.decrypt(row.refresh_token_encrypted)
                if row.refresh_token_encrypted
                else None
            ),
            scopes=list(row.scopes),
        )

    async def rotate_refresh_token(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, refresh_token: str
    ) -> None:
        await self._repo.update_refresh_token(
            tenant_id, connection_id, self._cipher.encrypt(refresh_token)
        )
        await self._audit.emit(
            tenant_id,
            "credential.rotate_refresh_token",
            resource=str(connection_id),
        )
