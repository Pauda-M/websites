from __future__ import annotations

import uuid
from datetime import timedelta

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.calendar import CalendarEvent, TimeSlot
from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.domain.sync import WebhookSubscription
from pb_api.integrations.workspace.local import InMemoryStore, InMemoryWorkspaceProvider


async def test_webhook_create_and_due_for_renewal(
    ctx: WorkspaceContext,
    provider: InMemoryWorkspaceProvider,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    subscription = await provider.create_subscription(
        tenant,
        connection.id,
        WebhookSubscription(
            tenant_id=tenant,
            connection_id=connection.id,
            resource=f"/users/{connection.mailbox}/messages",
            notification_url="https://pb.example/webhooks/graph",
            client_state="secret",
        ),
    )
    assert subscription.provider_subscription_id is not None
    assert subscription.expires_at is not None
    stored = await ctx.webhooks.add(subscription)
    # Nothing is due far before expiry; everything is due far after.
    assert await ctx.webhooks.due_for_renewal(tenant, before=utcnow()) == []
    due = await ctx.webhooks.due_for_renewal(tenant, before=utcnow() + timedelta(days=30))
    assert [item.id for item in due] == [stored.id]


async def test_calendar_conflict_detection(
    ctx: WorkspaceContext,
    store: InMemoryStore,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    start = utcnow() + timedelta(days=1)
    store.seed_events(
        tenant,
        connection.id,
        [
            CalendarEvent(
                tenant_id=tenant,
                provider_id="e1",
                subject="Existing meeting",
                start=start,
                end=start + timedelta(hours=1),
            )
        ],
    )
    # A slot overlapping the existing event is flagged as conflicting.
    conflict = await ctx.calendar.detect_conflicts(
        tenant,
        connection.id,
        proposed=TimeSlot(start=start + timedelta(minutes=30), end=start + timedelta(hours=2)),
    )
    assert conflict.conflicting_event_ids == ["e1"]
    # A slot after the event is clear.
    clear = await ctx.calendar.detect_conflicts(
        tenant,
        connection.id,
        proposed=TimeSlot(start=start + timedelta(hours=3), end=start + timedelta(hours=4)),
    )
    assert clear.conflicting_event_ids == []
