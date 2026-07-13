"""Background synchronization worker.

Drives periodic delta synchronization and webhook renewal outside the request
path. A *tick* opens its own session, builds a :class:`WorkspaceContext`, syncs
every connection for a tenant (each resource with retry + dead-lettering), and
renews webhook subscriptions nearing expiry. A production scheduler invokes
``tick`` per tenant on an interval; the API can also trigger a tick on demand.

The worker takes an optional ``provider_for`` factory so it uses the same provider
adapter as the request path (the Microsoft Graph adapter in production, built from
the tick's own session); when omitted the context builds its default provider.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pb_api.core.logging import get_logger
from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.config import WorkspaceSettings, get_workspace_settings
from pb_api.integrations.workspace.ports.providers import WorkspaceProvider

logger = get_logger("pb_api.workspace.worker")

ProviderFactory = Callable[[AsyncSession], WorkspaceProvider]


class WorkspaceSyncWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        settings: WorkspaceSettings | None = None,
        provider_for: ProviderFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or get_workspace_settings()
        self._provider_for = provider_for

    async def tick(self, tenant_id: uuid.UUID) -> dict[str, int]:
        """Run one synchronization pass for a tenant; returns a run summary."""
        async with self._session_factory() as session:
            provider = self._provider_for(session) if self._provider_for is not None else None
            context = WorkspaceContext(session, provider=provider, settings=self._settings)
            connections = await context.list_connections(tenant_id)
            jobs = 0
            failures = 0
            for connection in connections:
                for job in await context.sync.sync_all(tenant_id, connection.id):
                    jobs += 1
                    if job.status.value == "failed":
                        failures += 1
            renewed = await context.renew_due_webhooks(tenant_id)
            await session.commit()
        summary = {
            "connections": len(connections),
            "jobs": jobs,
            "failures": failures,
            "webhooks_renewed": renewed,
        }
        logger.info("worker_tick", tenant_id=str(tenant_id), **summary)
        return summary
