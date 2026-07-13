from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.common import SyncResource, SyncStatus
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.domain.contacts import WorkspaceContact
from pb_api.integrations.workspace.domain.mail import EmailAddress, WorkspaceMessage
from pb_api.integrations.workspace.local import InMemoryStore, InMemoryWorkspaceProvider


def _fast_settings() -> WorkspaceSettings:
    return WorkspaceSettings(max_retries=2, retry_base_delay_seconds=0.0)


async def test_sync_all_succeeds_across_resources(
    ctx: WorkspaceContext,
    store: InMemoryStore,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    store.seed_messages(
        tenant,
        connection.id,
        [
            WorkspaceMessage(
                tenant_id=tenant,
                provider_id="m1",
                subject="Hello",
                body="hi",
                sender=EmailAddress(address="a@b.com"),
            )
        ],
    )
    store.seed_contacts(
        tenant,
        connection.id,
        [WorkspaceContact(tenant_id=tenant, provider_id="c1", display_name="Bob")],
    )
    jobs = await ctx.sync.sync_all(tenant, connection.id)
    assert len(jobs) == 5
    assert all(job.status is SyncStatus.SUCCEEDED for job in jobs)
    # Synced items were indexed for unified search.
    assert await ctx.search.search(tenant, query="Bob", kinds=["contact"])


async def test_exhausted_retries_dead_letter_and_failed_job(
    session: AsyncSession, store: InMemoryStore, tenant: uuid.UUID
) -> None:
    provider = InMemoryWorkspaceProvider(store)
    ctx = WorkspaceContext(session, provider=provider, settings=_fast_settings())
    connection = await ctx.bootstrap_connection(tenant, display_name="X", mailbox="x@y.com")

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("provider unavailable")

    failing: Callable[..., Awaitable[Any]] = boom
    provider.mail.delta_messages = failing  # type: ignore[assignment]

    job = await ctx.sync.sync_resource(tenant, connection.id, SyncResource.MAIL)
    assert job.status is SyncStatus.FAILED
    assert job.error is not None
    # The failed unit landed in the dead-letter queue — never silently lost.
    assert await ctx.dead_letters.count(tenant) == 1
    failures = await ctx.core.events.history(tenant, event_type="pb.workspace.sync.failed")
    assert len(failures) == 1
