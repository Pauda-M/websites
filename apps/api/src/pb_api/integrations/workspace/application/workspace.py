"""WorkspaceContext — the composition root for the workspace integration.

Assembles a chosen provider adapter, every repository, the Cognitive Core, the CRM
bridge, security (credential cipher + audit), and all services from a single
``AsyncSession``. This is the one place cross-context wiring happens: services
depend only on ports and repositories, and the CRM is reached through the narrow
bridge — no service imports a vendor SDK or another bounded context's internals.

The provider defaults to the fully-functional in-memory adapter so the platform
runs with no external credentials; production injects the Microsoft Graph adapter.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.agents.program_manager.application.program_manager import ProgramManager
from pb_api.cognitive.services import CognitiveCore
from pb_api.integrations.workspace.application.approval_engine import ApprovalEngine
from pb_api.integrations.workspace.application.audit_sink import DbAuditSink
from pb_api.integrations.workspace.application.calendar_service import CalendarService
from pb_api.integrations.workspace.application.collaboration import (
    NotificationService,
    PresenceService,
    TeamsService,
)
from pb_api.integrations.workspace.application.credential_store import EncryptedCredentialStore
from pb_api.integrations.workspace.application.crm_bridge import ProgramManagerCrmBridge
from pb_api.integrations.workspace.application.document_service import DocumentService
from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.mailbox_service import MailboxService
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.application.sync_service import SyncService
from pb_api.integrations.workspace.config import WorkspaceSettings, get_workspace_settings
from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.connection import ConnectionStatus, WorkspaceConnection
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.infrastructure.repositories import (
    ApprovalPolicyRepository,
    ApprovalRequestRepository,
    AuditRepository,
    ConnectionRepository,
    CredentialRepository,
    DeadLetterRepository,
    IndexEntryRepository,
    MailMessageRepository,
    SyncJobRepository,
    SyncStateRepository,
    WebhookSubscriptionRepository,
)
from pb_api.integrations.workspace.local import InMemoryWorkspaceProvider
from pb_api.integrations.workspace.ports.credentials import OAuthGrant
from pb_api.integrations.workspace.ports.providers import WorkspaceProvider
from pb_api.integrations.workspace.security.audit import AuditLog, AuditSink
from pb_api.integrations.workspace.security.crypto import CredentialCipher


class WorkspaceContext:
    """Composition root: every workspace service wired to one session + provider."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: WorkspaceProvider | None = None,
        settings: WorkspaceSettings | None = None,
        core: CognitiveCore | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_workspace_settings()
        self.core = core or CognitiveCore(session)
        self.provider: WorkspaceProvider = provider or InMemoryWorkspaceProvider()

        # CRM reached through the narrow bridge over the Program Manager's CRM.
        crm_bridge = ProgramManagerCrmBridge(ProgramManager(session, core=self.core).crm)

        # Repositories.
        self.connections = ConnectionRepository(session)
        self.credentials = CredentialRepository(session)
        self.webhooks = WebhookSubscriptionRepository(session)
        self.dead_letters = DeadLetterRepository(session)
        sync_state = SyncStateRepository(session)
        sync_jobs = SyncJobRepository(session)
        messages = MailMessageRepository(session)
        index = IndexEntryRepository(session)

        # Security.
        cipher = CredentialCipher.from_key_material(self.settings.credential_encryption_key)
        self.audit = AuditLog(audit_sink or DbAuditSink(AuditRepository(session)))
        self.credential_store = EncryptedCredentialStore(self.credentials, cipher, self.audit)

        # Cross-cutting services.
        self.projector = WorkspaceEventProjector(self.core.events, self.core.episodic)
        self.search = SearchService(index, self.settings)
        self.approvals = ApprovalEngine(
            ApprovalPolicyRepository(session),
            ApprovalRequestRepository(session),
            self.core.events,
            self.audit,
        )

        # Capability services.
        self.mailbox = MailboxService(
            provider=self.provider.mail,
            messages=messages,
            sync_state=sync_state,
            crm=crm_bridge,
            approvals=self.approvals,
            projector=self.projector,
            search=self.search,
            settings=self.settings,
        )
        self.calendar = CalendarService(
            provider=self.provider.calendar,
            approvals=self.approvals,
            projector=self.projector,
            search=self.search,
            settings=self.settings,
        )
        self.documents = DocumentService(
            provider=self.provider.storage,
            search=self.search,
            projector=self.projector,
            settings=self.settings,
        )
        self.teams = TeamsService(
            provider=self.provider.meetings,
            approvals=self.approvals,
            projector=self.projector,
            search=self.search,
        )
        self.presence = PresenceService(provider=self.provider.presence, projector=self.projector)
        self.notifications = NotificationService(
            provider=self.provider.notifications,
            approvals=self.approvals,
            projector=self.projector,
        )
        self.sync = SyncService(
            provider=self.provider,
            mailbox=self.mailbox,
            documents=self.documents,
            search=self.search,
            projector=self.projector,
            sync_state=sync_state,
            sync_jobs=sync_jobs,
            dead_letters=self.dead_letters,
            settings=self.settings,
        )

    # --- Connection lifecycle ------------------------------------------

    async def bootstrap_connection(
        self,
        tenant_id: uuid.UUID,
        *,
        display_name: str,
        mailbox: str,
        provider_tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str | None = None,
        scopes: builtins.list[str] | None = None,
    ) -> WorkspaceConnection:
        """Register a workspace connection, store its credentials, seed policies."""
        connection = await self.connections.add(
            WorkspaceConnection(
                tenant_id=tenant_id,
                provider=self.settings.provider,
                display_name=display_name,
                mailbox=mailbox,
                status=ConnectionStatus.ACTIVE,
            )
        )
        if client_id:
            await self.credential_store.save(
                OAuthGrant(
                    tenant_id=tenant_id,
                    connection_id=connection.id,
                    provider_tenant_id=provider_tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh_token,
                    scopes=scopes or self.settings.graph_scope_list,
                )
            )
        await self.approvals.seed_default_policies(tenant_id)
        await self.projector.project(
            tenant_id,
            event_type=WorkspaceEventType.CONNECTION_ESTABLISHED,
            summary=f"Workspace connection established: {display_name}",
            aggregate_id=connection.id,
            memorize=False,
            payload={"provider": self.settings.provider.value, "mailbox": mailbox},
        )
        return connection

    async def list_connections(self, tenant_id: uuid.UUID) -> builtins.list[WorkspaceConnection]:
        return await self.connections.list(tenant_id)

    # --- Webhook maintenance -------------------------------------------

    async def renew_due_webhooks(self, tenant_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Renew webhook subscriptions nearing expiry; returns the count renewed."""
        horizon = (now or utcnow()) + timedelta(seconds=self.settings.webhook_renew_before_seconds)
        due = await self.webhooks.due_for_renewal(tenant_id, before=horizon)
        for subscription in due:
            renewed = await self.provider.renew_subscription(
                tenant_id, subscription.connection_id, subscription
            )
            await self.webhooks.update(renewed)
        return len(due)

    async def health(self, tenant_id: uuid.UUID) -> dict[str, object]:
        """A workspace-health snapshot: provider reachability + queue/webhook state."""
        connections = await self.connections.list(tenant_id)
        reachable = True
        for connection in connections:
            reachable = reachable and await self.provider.healthcheck(tenant_id, connection.id)
        return {
            "provider": self.settings.provider.value,
            "connections": len(connections),
            "provider_reachable": reachable if connections else True,
            "dead_letters": await self.dead_letters.count(tenant_id),
            "active_webhooks": len(await self.webhooks.list(tenant_id, active_only=True)),
        }
