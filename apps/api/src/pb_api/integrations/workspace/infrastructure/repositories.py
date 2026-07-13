"""Tenant-scoped async repositories for the workspace integration.

One repository per workspace aggregate (connections, credentials, sync state/jobs,
the dead-letter queue, webhook subscriptions, approval policies/requests, the audit
log, mail messages, and the unified search index). Each subclasses
:class:`BaseRepository` and scopes every query by ``tenant_id`` — cross-tenant
access is impossible by construction (Genesis §12.6). Writes ``flush`` so generated
values are visible within the unit of work.

The credential repository is the one exception to the row<->domain mapping: it
returns the raw :class:`WorkspaceCredentialRow` because the ciphertext lives here
untouched — encryption/decryption belongs to the credential store adapter, never to
persistence.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select

from pb_api.cognitive.repositories.base import BaseRepository
from pb_api.integrations.workspace.db.models import (
    ApprovalPolicyRow,
    ApprovalRequestRow,
    AuditLogRow,
    DeadLetterRow,
    IndexEntryRow,
    MailMessageRow,
    SyncJobRow,
    SyncStateRow,
    WebhookSubscriptionRow,
    WorkspaceConnectionRow,
    WorkspaceCredentialRow,
)
from pb_api.integrations.workspace.domain.approval import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalRequestStatus,
    CommunicationType,
)
from pb_api.integrations.workspace.domain.common import (
    ApprovalDecisionType,
    MessagePriority,
    Provider,
    SyncResource,
    SyncStatus,
    utcnow,
)
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.domain.mail import (
    Attachment,
    EmailAddress,
    WorkspaceMessage,
)
from pb_api.integrations.workspace.domain.search import IndexEntry
from pb_api.integrations.workspace.domain.sync import (
    DeadLetter,
    SyncJob,
    SyncState,
    WebhookSubscription,
)
from pb_api.integrations.workspace.security.audit import AuditRecord

# --- Connection --------------------------------------------------------


def _row_to_connection(row: WorkspaceConnectionRow) -> WorkspaceConnection:
    return WorkspaceConnection(
        id=row.id,
        tenant_id=row.tenant_id,
        provider=Provider(row.provider),
        display_name=row.display_name,
        mailbox=row.mailbox,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ConnectionRepository(BaseRepository):
    async def add(self, connection: WorkspaceConnection) -> WorkspaceConnection:
        row = WorkspaceConnectionRow(
            id=connection.id,
            tenant_id=connection.tenant_id,
            provider=connection.provider.value,
            display_name=connection.display_name,
            mailbox=connection.mailbox,
            status=connection.status,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_connection(row)

    async def get(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> WorkspaceConnection | None:
        row = await self.session.get(WorkspaceConnectionRow, connection_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_connection(row)

    async def list(self, tenant_id: uuid.UUID, *, limit: int = 200) -> list[WorkspaceConnection]:
        stmt = (
            select(WorkspaceConnectionRow)
            .where(WorkspaceConnectionRow.tenant_id == tenant_id)
            .order_by(WorkspaceConnectionRow.created_at.asc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_connection(row) for row in rows]

    async def update(self, connection: WorkspaceConnection) -> WorkspaceConnection | None:
        row = await self.session.get(WorkspaceConnectionRow, connection.id)
        if row is None or row.tenant_id != connection.tenant_id:
            return None
        row.provider = connection.provider.value
        row.display_name = connection.display_name
        row.mailbox = connection.mailbox
        row.status = connection.status
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_connection(row)

    async def get_default(self, tenant_id: uuid.UUID) -> WorkspaceConnection | None:
        stmt = (
            select(WorkspaceConnectionRow)
            .where(
                WorkspaceConnectionRow.tenant_id == tenant_id,
                WorkspaceConnectionRow.status == "active",
            )
            .order_by(WorkspaceConnectionRow.created_at.asc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return _row_to_connection(row)


# --- Credential --------------------------------------------------------


class CredentialRepository(BaseRepository):
    """Persists and reads the ENCRYPTED credential row as-is; it never encrypts."""

    async def upsert(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        provider_tenant_id: str,
        client_id: str,
        client_secret_encrypted: str,
        refresh_token_encrypted: str | None,
        scopes: list[str],
    ) -> WorkspaceCredentialRow:
        row = await self._get_row(tenant_id, connection_id)
        if row is None:
            row = WorkspaceCredentialRow(
                tenant_id=tenant_id,
                connection_id=connection_id,
                provider_tenant_id=provider_tenant_id,
                client_id=client_id,
                client_secret_encrypted=client_secret_encrypted,
                refresh_token_encrypted=refresh_token_encrypted,
                scopes=list(scopes),
            )
            self.session.add(row)
        else:
            row.provider_tenant_id = provider_tenant_id
            row.client_id = client_id
            row.client_secret_encrypted = client_secret_encrypted
            row.refresh_token_encrypted = refresh_token_encrypted
            row.scopes = list(scopes)
            row.updated_at = utcnow()
        await self.session.flush()
        return row

    async def get(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> WorkspaceCredentialRow | None:
        return await self._get_row(tenant_id, connection_id)

    async def update_refresh_token(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        refresh_token_encrypted: str,
    ) -> WorkspaceCredentialRow | None:
        row = await self._get_row(tenant_id, connection_id)
        if row is None:
            return None
        row.refresh_token_encrypted = refresh_token_encrypted
        row.updated_at = utcnow()
        await self.session.flush()
        return row

    async def _get_row(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> WorkspaceCredentialRow | None:
        stmt = (
            select(WorkspaceCredentialRow)
            .where(
                WorkspaceCredentialRow.tenant_id == tenant_id,
                WorkspaceCredentialRow.connection_id == connection_id,
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()


# --- Sync state --------------------------------------------------------


def _row_to_sync_state(row: SyncStateRow) -> SyncState:
    return SyncState(
        id=row.id,
        tenant_id=row.tenant_id,
        connection_id=row.connection_id,
        resource=SyncResource(row.resource),
        delta_token=row.delta_token,
        status=SyncStatus(row.status),
        last_synced_at=row.last_synced_at,
        last_error=row.last_error,
        items_synced=row.items_synced,
        updated_at=row.updated_at,
    )


class SyncStateRepository(BaseRepository):
    async def get_or_create(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, resource: SyncResource
    ) -> SyncState:
        stmt = (
            select(SyncStateRow)
            .where(
                SyncStateRow.tenant_id == tenant_id,
                SyncStateRow.connection_id == connection_id,
                SyncStateRow.resource == resource.value,
            )
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            row = SyncStateRow(
                tenant_id=tenant_id,
                connection_id=connection_id,
                resource=resource.value,
                status=SyncStatus.IDLE.value,
                items_synced=0,
            )
            self.session.add(row)
            await self.session.flush()
        return _row_to_sync_state(row)

    async def update(self, state: SyncState) -> SyncState:
        row = await self.session.get(SyncStateRow, state.id)
        if row is None or row.tenant_id != state.tenant_id:
            raise LookupError(f"sync state {state.id} not found for tenant {state.tenant_id}")
        row.delta_token = state.delta_token
        row.status = state.status.value
        row.last_synced_at = state.last_synced_at
        row.last_error = state.last_error
        row.items_synced = state.items_synced
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_sync_state(row)

    async def list(
        self, tenant_id: uuid.UUID, *, connection_id: uuid.UUID | None = None
    ) -> list[SyncState]:
        stmt = select(SyncStateRow).where(SyncStateRow.tenant_id == tenant_id)
        if connection_id is not None:
            stmt = stmt.where(SyncStateRow.connection_id == connection_id)
        stmt = stmt.order_by(SyncStateRow.updated_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_sync_state(row) for row in rows]


# --- Sync job ----------------------------------------------------------


def _row_to_sync_job(row: SyncJobRow) -> SyncJob:
    return SyncJob(
        id=row.id,
        tenant_id=row.tenant_id,
        connection_id=row.connection_id,
        resource=SyncResource(row.resource),
        status=SyncStatus(row.status),
        items_processed=row.items_processed,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
    )


class SyncJobRepository(BaseRepository):
    async def add(self, job: SyncJob) -> SyncJob:
        row = SyncJobRow(
            id=job.id,
            tenant_id=job.tenant_id,
            connection_id=job.connection_id,
            resource=job.resource.value,
            status=job.status.value,
            items_processed=job.items_processed,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=job.error,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_sync_job(row)

    async def finish(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        status: SyncStatus,
        items_processed: int,
        error: str | None = None,
    ) -> SyncJob:
        row = await self.session.get(SyncJobRow, job_id)
        if row is None or row.tenant_id != tenant_id:
            raise LookupError(f"sync job {job_id} not found for tenant {tenant_id}")
        row.status = status.value
        row.items_processed = items_processed
        row.error = error
        row.finished_at = utcnow()
        await self.session.flush()
        return _row_to_sync_job(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        connection_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[SyncJob]:
        stmt = select(SyncJobRow).where(SyncJobRow.tenant_id == tenant_id)
        if connection_id is not None:
            stmt = stmt.where(SyncJobRow.connection_id == connection_id)
        stmt = stmt.order_by(SyncJobRow.started_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_sync_job(row) for row in rows]


# --- Dead-letter queue -------------------------------------------------


def _row_to_dead_letter(row: DeadLetterRow) -> DeadLetter:
    return DeadLetter(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=row.kind,
        payload=dict(row.payload),
        error=row.error,
        attempts=row.attempts,
        created_at=row.created_at,
    )


class DeadLetterRepository(BaseRepository):
    async def add(self, dead_letter: DeadLetter) -> DeadLetter:
        row = DeadLetterRow(
            id=dead_letter.id,
            tenant_id=dead_letter.tenant_id,
            kind=dead_letter.kind,
            payload=dead_letter.payload,
            error=dead_letter.error,
            attempts=dead_letter.attempts,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_dead_letter(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetter]:
        stmt = select(DeadLetterRow).where(DeadLetterRow.tenant_id == tenant_id)
        if kind is not None:
            stmt = stmt.where(DeadLetterRow.kind == kind)
        stmt = stmt.order_by(DeadLetterRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_dead_letter(row) for row in rows]

    async def count(self, tenant_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(DeadLetterRow)
            .where(DeadLetterRow.tenant_id == tenant_id)
        )
        return int((await self.session.execute(stmt)).scalar_one())


# --- Webhook subscription ----------------------------------------------


def _row_to_webhook_subscription(row: WebhookSubscriptionRow) -> WebhookSubscription:
    return WebhookSubscription(
        id=row.id,
        tenant_id=row.tenant_id,
        connection_id=row.connection_id,
        provider=Provider(row.provider),
        provider_subscription_id=row.provider_subscription_id,
        resource=row.resource,
        change_types=[str(item) for item in row.change_types],
        notification_url=row.notification_url,
        client_state=row.client_state,
        expires_at=row.expires_at,
        active=row.active,
        created_at=row.created_at,
    )


class WebhookSubscriptionRepository(BaseRepository):
    async def add(self, subscription: WebhookSubscription) -> WebhookSubscription:
        row = WebhookSubscriptionRow(
            id=subscription.id,
            tenant_id=subscription.tenant_id,
            connection_id=subscription.connection_id,
            provider=subscription.provider.value,
            provider_subscription_id=subscription.provider_subscription_id,
            resource=subscription.resource,
            change_types=list(subscription.change_types),
            notification_url=subscription.notification_url,
            client_state=subscription.client_state,
            expires_at=subscription.expires_at,
            active=subscription.active,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_webhook_subscription(row)

    async def get(
        self, tenant_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> WebhookSubscription | None:
        row = await self.session.get(WebhookSubscriptionRow, subscription_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_webhook_subscription(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        connection_id: uuid.UUID | None = None,
        active_only: bool = True,
    ) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscriptionRow).where(WebhookSubscriptionRow.tenant_id == tenant_id)
        if connection_id is not None:
            stmt = stmt.where(WebhookSubscriptionRow.connection_id == connection_id)
        if active_only:
            stmt = stmt.where(WebhookSubscriptionRow.active.is_(True))
        stmt = stmt.order_by(WebhookSubscriptionRow.created_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_webhook_subscription(row) for row in rows]

    async def update(self, subscription: WebhookSubscription) -> WebhookSubscription | None:
        row = await self.session.get(WebhookSubscriptionRow, subscription.id)
        if row is None or row.tenant_id != subscription.tenant_id:
            return None
        row.provider = subscription.provider.value
        row.provider_subscription_id = subscription.provider_subscription_id
        row.resource = subscription.resource
        row.change_types = list(subscription.change_types)
        row.notification_url = subscription.notification_url
        row.client_state = subscription.client_state
        row.expires_at = subscription.expires_at
        row.active = subscription.active
        await self.session.flush()
        return _row_to_webhook_subscription(row)

    async def delete(self, tenant_id: uuid.UUID, subscription_id: uuid.UUID) -> bool:
        row = await self.session.get(WebhookSubscriptionRow, subscription_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def due_for_renewal(
        self, tenant_id: uuid.UUID, *, before: datetime
    ) -> builtins.list[WebhookSubscription]:
        stmt = (
            select(WebhookSubscriptionRow)
            .where(
                WebhookSubscriptionRow.tenant_id == tenant_id,
                WebhookSubscriptionRow.active.is_(True),
                WebhookSubscriptionRow.expires_at.is_not(None),
                WebhookSubscriptionRow.expires_at <= before,
            )
            .order_by(WebhookSubscriptionRow.expires_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_webhook_subscription(row) for row in rows]


# --- Approval policy ---------------------------------------------------


def _row_to_approval_policy(row: ApprovalPolicyRow) -> ApprovalPolicy:
    return ApprovalPolicy(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        decision=ApprovalDecisionType(row.decision),
        communication_type=(
            CommunicationType(row.communication_type)
            if row.communication_type is not None
            else None
        ),
        customer_organization_id=row.customer_organization_id,
        customer_contact_id=row.customer_contact_id,
        agent_id=row.agent_id,
        min_authority=row.min_authority,
        priority=row.priority,
        enabled=row.enabled,
        description=row.description,
        created_at=row.created_at,
    )


class ApprovalPolicyRepository(BaseRepository):
    async def add(self, policy: ApprovalPolicy) -> ApprovalPolicy:
        row = ApprovalPolicyRow(
            id=policy.id,
            tenant_id=policy.tenant_id,
            name=policy.name,
            decision=policy.decision.value,
            communication_type=(
                policy.communication_type.value if policy.communication_type is not None else None
            ),
            customer_organization_id=policy.customer_organization_id,
            customer_contact_id=policy.customer_contact_id,
            agent_id=policy.agent_id,
            min_authority=policy.min_authority,
            priority=policy.priority,
            enabled=policy.enabled,
            description=policy.description,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_approval_policy(row)

    async def list(
        self, tenant_id: uuid.UUID, *, enabled_only: bool = True
    ) -> list[ApprovalPolicy]:
        stmt = select(ApprovalPolicyRow).where(ApprovalPolicyRow.tenant_id == tenant_id)
        if enabled_only:
            stmt = stmt.where(ApprovalPolicyRow.enabled.is_(True))
        stmt = stmt.order_by(ApprovalPolicyRow.priority.asc(), ApprovalPolicyRow.created_at.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_approval_policy(row) for row in rows]

    async def delete(self, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> bool:
        row = await self.session.get(ApprovalPolicyRow, policy_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


# --- Approval request --------------------------------------------------


def _row_to_approval_request(row: ApprovalRequestRow) -> ApprovalRequest:
    return ApprovalRequest(
        id=row.id,
        tenant_id=row.tenant_id,
        communication_type=CommunicationType(row.communication_type),
        status=ApprovalRequestStatus(row.status),
        summary=row.summary,
        customer_organization_id=row.customer_organization_id,
        agent_id=row.agent_id,
        payload=dict(row.payload),
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


class ApprovalRequestRepository(BaseRepository):
    async def add(self, request: ApprovalRequest) -> ApprovalRequest:
        row = ApprovalRequestRow(
            id=request.id,
            tenant_id=request.tenant_id,
            communication_type=request.communication_type.value,
            status=request.status.value,
            summary=request.summary,
            customer_organization_id=request.customer_organization_id,
            agent_id=request.agent_id,
            payload=request.payload,
            decided_by=request.decided_by,
            decided_at=request.decided_at,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_approval_request(row)

    async def get(self, tenant_id: uuid.UUID, request_id: uuid.UUID) -> ApprovalRequest | None:
        row = await self.session.get(ApprovalRequestRow, request_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_approval_request(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: ApprovalRequestStatus | None = None,
        limit: int = 200,
    ) -> list[ApprovalRequest]:
        stmt = select(ApprovalRequestRow).where(ApprovalRequestRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(ApprovalRequestRow.status == status.value)
        stmt = stmt.order_by(ApprovalRequestRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_approval_request(row) for row in rows]

    async def update(self, request: ApprovalRequest) -> ApprovalRequest | None:
        row = await self.session.get(ApprovalRequestRow, request.id)
        if row is None or row.tenant_id != request.tenant_id:
            return None
        row.communication_type = request.communication_type.value
        row.status = request.status.value
        row.summary = request.summary
        row.customer_organization_id = request.customer_organization_id
        row.agent_id = request.agent_id
        row.payload = request.payload
        row.decided_by = request.decided_by
        row.decided_at = request.decided_at
        await self.session.flush()
        return _row_to_approval_request(row)


# --- Audit log ---------------------------------------------------------


def _row_to_audit_record(row: AuditLogRow) -> AuditRecord:
    return AuditRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        action=row.action,
        actor=row.actor,
        resource=row.resource,
        outcome=row.outcome,
        detail=dict(row.detail),
        created_at=row.created_at,
    )


class AuditRepository(BaseRepository):
    async def add(self, record: AuditRecord) -> AuditRecord:
        row = AuditLogRow(
            id=record.id,
            tenant_id=record.tenant_id,
            action=record.action,
            actor=record.actor,
            resource=record.resource,
            outcome=record.outcome,
            detail=record.detail,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_audit_record(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        action: str | None = None,
        limit: int = 200,
    ) -> list[AuditRecord]:
        stmt = select(AuditLogRow).where(AuditLogRow.tenant_id == tenant_id)
        if action is not None:
            stmt = stmt.where(AuditLogRow.action == action)
        stmt = stmt.order_by(AuditLogRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_audit_record(row) for row in rows]


# --- Mail message ------------------------------------------------------


def _row_to_message(row: MailMessageRow) -> WorkspaceMessage:
    return WorkspaceMessage(
        id=row.id,
        tenant_id=row.tenant_id,
        provider_id=row.provider_id,
        conversation_id=row.conversation_id,
        internet_message_id=row.internet_message_id,
        subject=row.subject,
        body_preview=row.body_preview,
        body=row.body,
        is_html=row.is_html,
        sender=EmailAddress(address=row.sender_address, name=row.sender_name),
        to=[EmailAddress.model_validate(item) for item in row.recipients_to],
        cc=[EmailAddress.model_validate(item) for item in row.recipients_cc],
        received_at=row.received_at,
        priority=MessagePriority(row.priority),
        is_read=row.is_read,
        is_flagged=row.is_flagged,
        categories=[str(item) for item in row.categories],
        folder=row.folder,
        has_attachments=row.has_attachments,
        attachments=[Attachment.model_validate(item) for item in row.attachments],
        customer_organization_id=row.customer_organization_id,
        customer_contact_id=row.customer_contact_id,
        metadata=dict(row.meta),
    )


class MailMessageRepository(BaseRepository):
    async def upsert(self, message: WorkspaceMessage) -> WorkspaceMessage:
        row = await self._get_row(message.tenant_id, message.provider_id)
        if row is None:
            row = MailMessageRow(
                id=message.id,
                tenant_id=message.tenant_id,
                provider_id=message.provider_id,
            )
            self.session.add(row)
        row.conversation_id = message.conversation_id
        row.internet_message_id = message.internet_message_id
        row.subject = message.subject
        row.body_preview = message.body_preview
        row.body = message.body
        row.is_html = message.is_html
        row.sender_address = message.sender.address
        row.sender_name = message.sender.name
        row.recipients_to = [address.model_dump(mode="json") for address in message.to]
        row.recipients_cc = [address.model_dump(mode="json") for address in message.cc]
        row.received_at = message.received_at
        row.priority = message.priority.value
        row.is_read = message.is_read
        row.is_flagged = message.is_flagged
        row.categories = list(message.categories)
        row.folder = message.folder
        row.has_attachments = message.has_attachments
        row.attachments = [attachment.model_dump(mode="json") for attachment in message.attachments]
        row.customer_organization_id = message.customer_organization_id
        row.customer_contact_id = message.customer_contact_id
        row.meta = message.metadata
        await self.session.flush()
        return _row_to_message(row)

    async def get_by_provider_id(
        self, tenant_id: uuid.UUID, provider_id: str
    ) -> WorkspaceMessage | None:
        row = await self._get_row(tenant_id, provider_id)
        if row is None:
            return None
        return _row_to_message(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        folder: str | None = None,
        limit: int = 100,
    ) -> list[WorkspaceMessage]:
        stmt = select(MailMessageRow).where(MailMessageRow.tenant_id == tenant_id)
        if folder is not None:
            stmt = stmt.where(MailMessageRow.folder == folder)
        stmt = stmt.order_by(MailMessageRow.received_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in rows]

    async def by_conversation(
        self, tenant_id: uuid.UUID, conversation_id: str
    ) -> builtins.list[WorkspaceMessage]:
        stmt = (
            select(MailMessageRow)
            .where(
                MailMessageRow.tenant_id == tenant_id,
                MailMessageRow.conversation_id == conversation_id,
            )
            .order_by(MailMessageRow.received_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in rows]

    async def search(
        self, tenant_id: uuid.UUID, query: str, *, limit: int = 50
    ) -> builtins.list[WorkspaceMessage]:
        pattern = f"%{query}%"
        stmt = (
            select(MailMessageRow)
            .where(
                MailMessageRow.tenant_id == tenant_id,
                or_(
                    MailMessageRow.subject.ilike(pattern),
                    MailMessageRow.body.ilike(pattern),
                ),
            )
            .order_by(MailMessageRow.received_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in rows]

    async def _get_row(self, tenant_id: uuid.UUID, provider_id: str) -> MailMessageRow | None:
        stmt = (
            select(MailMessageRow)
            .where(
                MailMessageRow.tenant_id == tenant_id,
                MailMessageRow.provider_id == provider_id,
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()


# --- Unified search index ----------------------------------------------


def _row_to_index_entry(row: IndexEntryRow) -> IndexEntry:
    return IndexEntry(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=row.kind,
        source_provider_id=row.source_provider_id,
        connection_id=row.connection_id,
        title=row.title,
        snippet=row.snippet,
        body=row.body,
        web_url=row.web_url,
        embedding=list(row.embedding),
        ref=dict(row.ref),
        indexed_at=row.indexed_at,
    )


class IndexEntryRepository(BaseRepository):
    async def upsert(self, entry: IndexEntry) -> IndexEntry:
        row = await self._get_row(entry.tenant_id, entry.kind, entry.source_provider_id)
        if row is None:
            row = IndexEntryRow(
                id=entry.id,
                tenant_id=entry.tenant_id,
                kind=entry.kind,
                source_provider_id=entry.source_provider_id,
            )
            self.session.add(row)
        row.connection_id = entry.connection_id
        row.title = entry.title
        row.snippet = entry.snippet
        row.body = entry.body
        row.web_url = entry.web_url
        row.embedding = list(entry.embedding)
        row.ref = entry.ref
        row.indexed_at = entry.indexed_at
        await self.session.flush()
        return _row_to_index_entry(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[IndexEntry]:
        stmt = select(IndexEntryRow).where(IndexEntryRow.tenant_id == tenant_id)
        if kind is not None:
            stmt = stmt.where(IndexEntryRow.kind == kind)
        stmt = stmt.order_by(IndexEntryRow.indexed_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_index_entry(row) for row in rows]

    async def fetch_all(
        self,
        tenant_id: uuid.UUID,
        *,
        kinds: builtins.list[str] | None = None,
        limit: int = 1000,
    ) -> builtins.list[IndexEntry]:
        stmt = select(IndexEntryRow).where(IndexEntryRow.tenant_id == tenant_id)
        if kinds is not None:
            stmt = stmt.where(IndexEntryRow.kind.in_(kinds))
        stmt = stmt.order_by(IndexEntryRow.indexed_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_index_entry(row) for row in rows]

    async def _get_row(
        self, tenant_id: uuid.UUID, kind: str, source_provider_id: str
    ) -> IndexEntryRow | None:
        stmt = (
            select(IndexEntryRow)
            .where(
                IndexEntryRow.tenant_id == tenant_id,
                IndexEntryRow.kind == kind,
                IndexEntryRow.source_provider_id == source_provider_id,
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()
