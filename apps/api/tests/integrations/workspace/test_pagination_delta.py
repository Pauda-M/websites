from __future__ import annotations

import uuid

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.domain.mail import EmailAddress, WorkspaceMessage
from pb_api.integrations.workspace.local import InMemoryStore, InMemoryWorkspaceProvider


def _seed(store: InMemoryStore, tenant: uuid.UUID, connection_id: uuid.UUID, n: int) -> None:
    store.seed_messages(
        tenant,
        connection_id,
        [
            WorkspaceMessage(
                tenant_id=tenant,
                provider_id=f"m{i}",
                subject=f"Message {i}",
                sender=EmailAddress(address="a@b.com"),
            )
            for i in range(n)
        ],
    )


async def test_pagination_walks_all_pages(
    provider: InMemoryWorkspaceProvider,
    store: InMemoryStore,
    ctx: WorkspaceContext,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    _seed(store, tenant, connection.id, 5)
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = await provider.mail.list_messages(tenant, connection.id, cursor=cursor, page_size=2)
        seen.extend(message.provider_id for message in page.items)
        pages += 1
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert pages == 3  # 2 + 2 + 1
    assert sorted(seen) == [f"m{i}" for i in range(5)]


async def test_delta_returns_only_changes_after_token(
    provider: InMemoryWorkspaceProvider,
    store: InMemoryStore,
    ctx: WorkspaceContext,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    _seed(store, tenant, connection.id, 3)
    # First sweep: everything, then a delta token.
    first = await provider.mail.delta_messages(tenant, connection.id)
    assert len(first.items) == 3
    assert first.delta_token is not None

    # No changes → an empty delta.
    empty = await provider.mail.delta_messages(tenant, connection.id, delta_token=first.delta_token)
    assert list(empty.items) == []

    # Seed one more; the next delta returns only it.
    store.seed_messages(
        tenant,
        connection.id,
        [
            WorkspaceMessage(
                tenant_id=tenant,
                provider_id="m99",
                subject="new",
                sender=EmailAddress(address="a@b.com"),
            )
        ],
    )
    changed = await provider.mail.delta_messages(
        tenant, connection.id, delta_token=first.delta_token
    )
    assert [message.provider_id for message in changed.items] == ["m99"]
