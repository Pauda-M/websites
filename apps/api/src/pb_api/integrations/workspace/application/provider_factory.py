"""Provider factory — builds the Microsoft Graph adapter for production wiring.

The composition root and API layer depend on the ``WorkspaceProvider`` port; this
factory is the one place that constructs the concrete Graph adapter, wiring the
per-session encrypted credential store and a DB-backed resource resolver to the
app-scoped HTTP client and rate limiter. The in-memory adapter needs no factory
(it is instantiated directly). Selecting a provider is configuration, not code —
adding Google Workspace later means one more branch here and a new adapter package.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.integrations.workspace.application.audit_sink import DbAuditSink
from pb_api.integrations.workspace.application.credential_store import EncryptedCredentialStore
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.graph import (
    GraphClient,
    GraphTokenProvider,
    GraphWorkspaceProvider,
)
from pb_api.integrations.workspace.graph.rate_limit import AsyncRateLimiter
from pb_api.integrations.workspace.graph.resolver import ResourceBinding
from pb_api.integrations.workspace.infrastructure.repositories import (
    AuditRepository,
    ConnectionRepository,
    CredentialRepository,
)
from pb_api.integrations.workspace.ports.providers import WorkspaceProvider
from pb_api.integrations.workspace.security.audit import AuditLog
from pb_api.integrations.workspace.security.crypto import CredentialCipher


class DbGraphResolver:
    """Resolves a ``(tenant, connection)`` to its Graph resource ids from the DB.

    The connection's ``mailbox`` is both the mail user and the default user; the
    primary drive id, when present, is carried on the connection's metadata.
    """

    def __init__(self, connections: ConnectionRepository) -> None:
        self._connections = connections

    async def _binding(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> ResourceBinding:
        connection = await self._connections.get(tenant_id, connection_id)
        if connection is None:
            raise LookupError(f"workspace connection {connection_id} not found")
        # The primary drive resolves to the mailbox user's default drive; a
        # per-connection override can be introduced without touching callers.
        return ResourceBinding(mailbox=connection.mailbox)

    async def mailbox(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        return (await self._binding(tenant_id, connection_id)).mailbox

    async def drive(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        return (await self._binding(tenant_id, connection_id)).drive_id

    async def default_user(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        return (await self._binding(tenant_id, connection_id)).user()


def build_graph_provider(
    session: AsyncSession,
    settings: WorkspaceSettings,
    *,
    http_client: httpx.AsyncClient,
    rate_limiter: AsyncRateLimiter,
) -> WorkspaceProvider:
    """Construct the Microsoft Graph workspace provider for a session."""
    cipher = CredentialCipher.from_key_material(settings.credential_encryption_key)
    audit = AuditLog(DbAuditSink(AuditRepository(session)))
    credential_store = EncryptedCredentialStore(CredentialRepository(session), cipher, audit)
    token_provider = GraphTokenProvider(credential_store, http_client, settings)
    client = GraphClient(http_client, token_provider, rate_limiter, settings)
    resolver = DbGraphResolver(ConnectionRepository(session))
    return GraphWorkspaceProvider(client, resolver, settings)
