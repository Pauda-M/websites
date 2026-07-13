"""Collaboration services — Teams, presence, and notifications.

Thin services over the ``MeetingProvider`` (Teams), ``PresenceProvider``, and
``NotificationProvider`` ports. Posting to Teams and sending a notification are
outbound actions and pass the approval engine; reads and presence lookups do not.
Teams messages are indexed for unified search and become Genesis events.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.integrations.workspace.application.approval_engine import ApprovalEngine
from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.domain.approval import CommunicationType, OutboundAction
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.domain.presence import Notification, Presence
from pb_api.integrations.workspace.domain.teams import TeamsChannel, TeamsMessage
from pb_api.integrations.workspace.ports.providers import (
    MeetingProvider,
    NotificationProvider,
    PresenceProvider,
)


class TeamsService:
    def __init__(
        self,
        *,
        provider: MeetingProvider,
        approvals: ApprovalEngine,
        projector: WorkspaceEventProjector,
        search: SearchService,
    ) -> None:
        self._provider = provider
        self._approvals = approvals
        self._projector = projector
        self._search = search

    async def list_channels(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, team_provider_id: str
    ) -> builtins.list[TeamsChannel]:
        return await self._provider.list_channels(
            tenant_id, connection_id, team_provider_id=team_provider_id
        )

    async def list_messages(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, conversation_provider_id: str
    ) -> builtins.list[TeamsMessage]:
        page = await self._provider.list_messages(
            tenant_id, connection_id, conversation_provider_id=conversation_provider_id
        )
        for message in page.items:
            await self._search.index_text(
                tenant_id,
                kind="teams",
                source_provider_id=message.provider_id,
                title="Teams message",
                body=message.body,
                connection_id=connection_id,
            )
        return list(page.items)

    async def post_message(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        message: TeamsMessage,
        agent_id: uuid.UUID | None = None,
        actor_authority: int = 0,
    ) -> dict[str, object]:
        decision, request = await self._approvals.submit(
            OutboundAction(
                tenant_id=tenant_id,
                communication_type=CommunicationType.TEAMS_MESSAGE,
                actor_authority=actor_authority,
                agent_id=agent_id,
                summary="Teams message",
            )
        )
        if not decision.is_automatic:
            return {"decision": decision, "posted": False, "approval_request": request}
        provider_id = await self._provider.post_message(tenant_id, connection_id, message)
        return {"decision": decision, "posted": True, "provider_id": provider_id}


class PresenceService:
    def __init__(self, *, provider: PresenceProvider, projector: WorkspaceEventProjector) -> None:
        self._provider = provider
        self._projector = projector

    async def get_presence(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        user_provider_ids: builtins.list[str],
    ) -> builtins.list[Presence]:
        results = await self._provider.get_presence(
            tenant_id, connection_id, user_provider_ids=user_provider_ids
        )
        for presence in results:
            await self._projector.project(
                tenant_id,
                event_type=WorkspaceEventType.PRESENCE_CHANGED,
                summary=f"Presence {presence.user_provider_id}: {presence.availability.value}",
                memorize=False,
                payload={"availability": presence.availability.value},
            )
        return results


class NotificationService:
    def __init__(
        self,
        *,
        provider: NotificationProvider,
        approvals: ApprovalEngine,
        projector: WorkspaceEventProjector,
    ) -> None:
        self._provider = provider
        self._approvals = approvals
        self._projector = projector

    async def send(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        notification: Notification,
        actor_authority: int = 0,
    ) -> dict[str, object]:
        decision, request = await self._approvals.submit(
            OutboundAction(
                tenant_id=tenant_id,
                communication_type=CommunicationType.NOTIFICATION,
                actor_authority=actor_authority,
                summary=notification.title,
            )
        )
        if not decision.is_automatic:
            return {"decision": decision, "sent": False, "approval_request": request}
        provider_id = await self._provider.send(tenant_id, connection_id, notification)
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.NOTIFICATION_SENT,
            summary=f"Notification: {notification.title}",
            memorize=False,
            payload={"channel": notification.channel},
        )
        return {"decision": decision, "sent": True, "provider_id": provider_id}
