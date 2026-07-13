"""Mailbox service — the shared mailbox as a governed Genesis surface.

Reads and threads mail, identifies the customer and links it to the CRM, indexes
every message for unified search, and turns each message into a Genesis event that
updates memory. Outbound actions (reply / reply-all / forward) pass the approval
engine before anything leaves the building — an auto-approved reply is sent, a
draft-only or approval-required reply is prepared and queued. Business logic here
depends only on the ``MailProvider`` port, never on Microsoft Graph.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.integrations.workspace.application.approval_engine import ApprovalEngine
from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.approval import CommunicationType, OutboundAction
from pb_api.integrations.workspace.domain.common import MessagePriority, SyncResource
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.domain.mail import DraftReply, EmailAddress, WorkspaceMessage
from pb_api.integrations.workspace.domain.sync import SyncState
from pb_api.integrations.workspace.infrastructure.repositories import (
    MailMessageRepository,
    SyncStateRepository,
)
from pb_api.integrations.workspace.ports.crm_sync import CrmSyncPort
from pb_api.integrations.workspace.ports.providers import MailProvider

_URGENT_TERMS = ("urgent", "asap", "immediately", "critical", "emergency", "escalat")


def detect_priority(message: WorkspaceMessage) -> MessagePriority:
    """Deterministic priority detection: provider signal, then urgent-term scan."""
    if message.priority in (MessagePriority.HIGH, MessagePriority.URGENT):
        return message.priority
    haystack = f"{message.subject}\n{message.body_preview}".lower()
    if any(term in haystack for term in _URGENT_TERMS):
        return MessagePriority.HIGH
    return message.priority


class MailboxService:
    def __init__(
        self,
        *,
        provider: MailProvider,
        messages: MailMessageRepository,
        sync_state: SyncStateRepository,
        crm: CrmSyncPort,
        approvals: ApprovalEngine,
        projector: WorkspaceEventProjector,
        search: SearchService,
        settings: WorkspaceSettings,
    ) -> None:
        self._provider = provider
        self._messages = messages
        self._sync_state = sync_state
        self._crm = crm
        self._approvals = approvals
        self._projector = projector
        self._search = search
        self._settings = settings

    # --- Sync / ingestion ----------------------------------------------

    async def sync(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> SyncState:
        """Delta-sync the mailbox: ingest each new/changed message end-to-end."""
        state = await self._sync_state.get_or_create(tenant_id, connection_id, SyncResource.MAIL)
        cursor: str | None = None
        delta_token = state.delta_token
        processed = 0
        while True:
            page = await self._provider.delta_messages(
                tenant_id, connection_id, delta_token=delta_token, cursor=cursor
            )
            for message in page.items:
                await self.ingest(tenant_id, connection_id, message)
                processed += 1
            if page.delta_token is not None:
                state.delta_token = page.delta_token
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        state.items_synced += processed
        updated = await self._sync_state.update(state)
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.SYNC_COMPLETED,
            summary=f"Mailbox sync ingested {processed} message(s).",
            memorize=False,
            payload={"resource": SyncResource.MAIL.value, "count": processed},
        )
        return updated if updated is not None else state

    async def ingest(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message: WorkspaceMessage
    ) -> WorkspaceMessage:
        """Ingest one message: identify customer, link CRM, index, event + memory."""
        message.tenant_id = tenant_id
        message.priority = detect_priority(message)
        ref = await self._crm.ensure_customer(
            tenant_id,
            email=message.sender.address,
            display_name=message.sender.name,
        )
        message.customer_organization_id = ref.organization_id
        message.customer_contact_id = ref.contact_id
        stored = await self._messages.upsert(message)
        await self._crm.record_interaction(
            tenant_id,
            organization_id=ref.organization_id,
            summary=f"Email received: {message.subject or '(no subject)'}",
            actor="workspace:mail",
        )
        await self._search.index_text(
            tenant_id,
            kind="mail",
            source_provider_id=message.provider_id,
            title=message.subject,
            body=message.body or message.body_preview,
            web_url=None,
            connection_id=connection_id,
            ref={"conversation_id": message.conversation_id or ""},
        )
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MAIL_RECEIVED,
            summary=f"Email from {message.sender.address}: {message.subject or '(no subject)'}",
            aggregate_id=stored.id,
            customer=ref.organization_id,
            importance=0.7 if message.priority is MessagePriority.HIGH else 0.5,
            payload={
                "from": message.sender.address,
                "priority": message.priority.value,
                "conversation_id": message.conversation_id or "",
            },
        )
        return stored

    # --- Reads ---------------------------------------------------------

    async def list_messages(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, folder: str = "inbox"
    ) -> builtins.list[WorkspaceMessage]:
        page = await self._provider.list_messages(
            tenant_id, connection_id, folder=folder, page_size=self._settings.sync_page_size
        )
        return list(page.items)

    async def conversation(
        self, tenant_id: uuid.UUID, conversation_id: str
    ) -> builtins.list[WorkspaceMessage]:
        return await self._messages.by_conversation(tenant_id, conversation_id)

    async def search(self, tenant_id: uuid.UUID, *, query: str) -> builtins.list[WorkspaceMessage]:
        return await self._messages.search(tenant_id, query)

    # --- Outbound (approval-gated) -------------------------------------

    async def prepare_reply(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        message_provider_id: str,
        body: str,
        kind: str = "reply",
        agent_id: uuid.UUID | None = None,
        actor_authority: int = 0,
    ) -> dict[str, object]:
        """Prepare a reply and run it through the approval engine.

        Returns the decision and what happened: auto-approved replies are sent;
        draft/approval-required replies are stored as a provider draft and queued.
        """
        source = await self._messages.get_by_provider_id(tenant_id, message_provider_id)
        org_id = source.customer_organization_id if source is not None else None
        contact_id = source.customer_contact_id if source is not None else None
        recipients: list[EmailAddress] = [source.sender] if source is not None else []
        draft = DraftReply(
            tenant_id=tenant_id,
            kind=kind,
            in_reply_to_provider_id=message_provider_id,
            conversation_id=source.conversation_id if source is not None else None,
            to=recipients,
            subject=f"RE: {source.subject}" if source is not None else "",
            body=body,
        )
        comm_type = (
            CommunicationType.MAIL_FORWARD if kind == "forward" else CommunicationType.MAIL_REPLY
        )
        decision, request = await self._approvals.submit(
            OutboundAction(
                tenant_id=tenant_id,
                communication_type=comm_type,
                actor_authority=actor_authority,
                agent_id=agent_id,
                customer_organization_id=org_id,
                customer_contact_id=contact_id,
                summary=f"{kind} to {recipients[0].address if recipients else 'customer'}",
                payload={"message_provider_id": message_provider_id},
            )
        )
        if decision.is_automatic:
            provider_message_id = await self._provider.send(tenant_id, connection_id, draft)
            await self._projector.project(
                tenant_id,
                event_type=WorkspaceEventType.MAIL_SENT,
                summary=f"Sent {kind}: {draft.subject}",
                customer=org_id,
                payload={"provider_message_id": provider_message_id},
            )
            return {"decision": decision, "sent": True, "provider_message_id": provider_message_id}
        prepared = await self._provider.create_draft(tenant_id, connection_id, draft)
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MAIL_DRAFT_CREATED,
            summary=f"Drafted {kind}: {draft.subject}",
            customer=org_id,
            memorize=False,
            payload={"provider_draft_id": prepared.provider_draft_id or ""},
        )
        return {
            "decision": decision,
            "sent": False,
            "draft": prepared,
            "approval_request": request,
        }

    async def categorize(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        message_provider_id: str,
        categories: builtins.list[str],
    ) -> None:
        await self._provider.set_categories(
            tenant_id, connection_id, message_provider_id, categories
        )
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MAIL_CATEGORIZED,
            summary=f"Categorized message {message_provider_id}",
            memorize=False,
            payload={"categories": categories},
        )

    async def move(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        message_provider_id: str,
        destination_folder: str,
    ) -> None:
        await self._provider.move(tenant_id, connection_id, message_provider_id, destination_folder)
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MAIL_MOVED,
            summary=f"Moved message {message_provider_id} to {destination_folder}",
            memorize=False,
            payload={"folder": destination_folder},
        )

    async def set_flag(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        message_provider_id: str,
        flagged: bool,
    ) -> None:
        await self._provider.set_flag(tenant_id, connection_id, message_provider_id, flagged)
