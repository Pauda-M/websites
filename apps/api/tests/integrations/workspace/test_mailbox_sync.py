from __future__ import annotations

import uuid

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.approval import ApprovalDecision, CommunicationType
from pb_api.integrations.workspace.domain.common import ApprovalDecisionType, MessagePriority
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.domain.mail import EmailAddress, WorkspaceMessage
from pb_api.integrations.workspace.local import InMemoryStore


def _seed_two(store: InMemoryStore, tenant: uuid.UUID, connection_id: uuid.UUID) -> None:
    store.seed_messages(
        tenant,
        connection_id,
        [
            WorkspaceMessage(
                tenant_id=tenant,
                provider_id="m1",
                conversation_id="c1",
                subject="URGENT: production is down",
                body="Please help immediately",
                sender=EmailAddress(address="jane@bigco.com", name="Jane Doe"),
            ),
            WorkspaceMessage(
                tenant_id=tenant,
                provider_id="m2",
                conversation_id="c1",
                subject="Re: production is down",
                body="Any update?",
                sender=EmailAddress(address="jane@bigco.com", name="Jane Doe"),
            ),
        ],
    )


async def test_sync_ingests_links_crm_events_memory_and_search(
    ctx: WorkspaceContext,
    store: InMemoryStore,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    _seed_two(store, tenant, connection.id)
    state = await ctx.mailbox.sync(tenant, connection.id)
    assert state.items_synced == 2

    # Priority detection flagged the urgent message (search "URGENT" matches only m1).
    urgent_hits = await ctx.mailbox.search(tenant, query="URGENT")
    assert len(urgent_hits) == 1
    urgent = urgent_hits[0]
    assert urgent.provider_id == "m1"
    assert urgent.priority is MessagePriority.HIGH
    assert urgent.customer_organization_id is not None  # CRM customer linked

    # Every email became a MailReceived event and updated memory.
    received = await ctx.core.events.history(tenant, event_type="pb.mail.message.received")
    assert len(received) == 2
    assert len(await ctx.core.episodic.recent(tenant)) >= 2

    # Conversation threading.
    thread = await ctx.mailbox.conversation(tenant, "c1")
    assert len(thread) == 2

    # Unified semantic search finds the mail.
    hits = await ctx.search.search(tenant, query="production outage", kinds=["mail"])
    assert hits and hits[0].score > 0


async def test_reply_is_drafted_by_default_and_sent_when_auto_approved(
    ctx: WorkspaceContext,
    store: InMemoryStore,
    tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    _seed_two(store, tenant, connection.id)
    await ctx.mailbox.sync(tenant, connection.id)

    # Default policy seeded during bootstrap drafts replies.
    drafted = await ctx.mailbox.prepare_reply(
        tenant, connection.id, message_provider_id="m1", body="On it now."
    )
    assert drafted["sent"] is False
    decision = drafted["decision"]
    assert isinstance(decision, ApprovalDecision)
    assert decision.decision is ApprovalDecisionType.CREATE_DRAFT

    # Add an auto-approve policy for replies → the reply is actually sent.
    from pb_api.integrations.workspace.domain.approval import ApprovalPolicy

    await ctx.approvals.add_policy(
        ApprovalPolicy(
            tenant_id=tenant,
            name="auto-replies",
            decision=ApprovalDecisionType.APPROVE_AUTOMATICALLY,
            communication_type=CommunicationType.MAIL_REPLY,
            priority=99,
        )
    )
    sent = await ctx.mailbox.prepare_reply(
        tenant, connection.id, message_provider_id="m1", body="Resolved."
    )
    assert sent["sent"] is True
    assert "provider_message_id" in sent
    mail_sent = await ctx.core.events.history(tenant, event_type="pb.mail.message.sent")
    assert len(mail_sent) == 1
