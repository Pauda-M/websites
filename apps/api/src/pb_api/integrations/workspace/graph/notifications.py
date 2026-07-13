"""Notification capability over Microsoft Graph.

An ``email`` notification is delivered with ``sendMail``; any other channel is
delivered as a Teams activity-feed notification
(``/users/{id}/teamwork/sendActivityNotification``), the supported way to surface
an actionable ping to a person.
"""

from __future__ import annotations

import uuid

from pb_api.integrations.workspace.domain.presence import Notification
from pb_api.integrations.workspace.graph.client import GraphClient
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver


class GraphNotificationsProvider:
    """Implements :class:`NotificationProvider` against mail / Teams activity feed."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def send(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, notification: Notification
    ) -> str:
        if notification.channel == "email":
            return await self._send_email(tenant_id, connection_id, notification)
        return await self._send_activity(tenant_id, connection_id, notification)

    async def _send_email(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, notification: Notification
    ) -> str:
        sender = await self._resolver.default_user(tenant_id, connection_id)
        content = notification.body or notification.title
        if notification.link:
            content = f"{content}\n\n{notification.link}"
        # Persist a draft first so a stable message id can be returned to the caller.
        draft = await self._client.post(
            f"/users/{sender}/messages",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={
                "subject": notification.title,
                "body": {"contentType": "text", "content": content},
                "toRecipients": [{"emailAddress": {"address": notification.recipient_provider_id}}],
            },
        )
        message_id = str(draft.json().get("id", ""))
        await self._client.post(
            f"/users/{sender}/messages/{message_id}/send",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        return message_id

    async def _send_activity(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, notification: Notification
    ) -> str:
        recipient = notification.recipient_provider_id
        preview = notification.body or notification.title
        await self._client.post(
            f"/users/{recipient}/teamwork/sendActivityNotification",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={
                "topic": {
                    "source": "text",
                    "value": notification.title,
                    "webUrl": notification.link or "https://teams.microsoft.com",
                },
                "activityType": "approvalRequired",
                "previewText": {"content": preview},
                "templateParameters": [{"name": "title", "value": notification.title}],
            },
        )
        # sendActivityNotification returns 204 with no id; the notification's own id
        # is the caller-facing handle.
        return str(notification.id)
