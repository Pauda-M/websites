"""Credential and token ports.

The OAuth flows Genesis supports (application/client-credentials and delegated with
refresh-token rotation) are modelled here as provider-agnostic value objects, and
the *storage* of credentials is a port so secrets can live in the environment, a
secret manager, or an encrypted database column without business logic caring.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from pb_api.integrations.workspace.domain.common import ensure_aware, utcnow


class OAuthGrant(BaseModel):
    """A stored OAuth credential for a workspace connection.

    ``client_secret`` and ``refresh_token`` are secrets and are only ever persisted
    encrypted (see the credential store). For application permissions the refresh
    token is absent; for delegated permissions it is present and rotated on refresh.
    """

    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    provider_tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str | None = None
    scopes: list[str] = Field(default_factory=list)


class AccessToken(BaseModel):
    """A short-lived access token with its expiry and (optionally) a rotated refresh."""

    token: str
    expires_at: datetime
    refresh_token: str | None = None

    def is_expired(self, *, skew_seconds: int = 60) -> bool:
        return ensure_aware(self.expires_at) <= utcnow() + timedelta(seconds=skew_seconds)


@runtime_checkable
class CredentialStore(Protocol):
    """Persists and retrieves OAuth grants for connections, secrets encrypted."""

    async def save(self, grant: OAuthGrant) -> None: ...

    async def load(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> OAuthGrant | None: ...

    async def rotate_refresh_token(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, refresh_token: str
    ) -> None: ...


@runtime_checkable
class TokenProvider(Protocol):
    """Acquires and refreshes access tokens for a connection (OAuth is hidden here)."""

    async def get_access_token(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> AccessToken: ...
