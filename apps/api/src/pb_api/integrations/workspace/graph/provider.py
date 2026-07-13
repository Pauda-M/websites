"""The aggregate Microsoft Graph workspace provider.

Composes the capability sub-providers behind the :class:`WorkspaceProvider` port
and owns the cross-capability concerns: a reachability healthcheck and the Graph
change-notification (webhook) subscription lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.common import Provider, utcnow
from pb_api.integrations.workspace.domain.sync import WebhookSubscription
from pb_api.integrations.workspace.graph.calendar import GraphCalendarProvider
from pb_api.integrations.workspace.graph.client import (
    GraphClient,
    parse_graph_datetime,
    to_graph_utc_iso,
)
from pb_api.integrations.workspace.graph.contacts import GraphContactsProvider
from pb_api.integrations.workspace.graph.directory import GraphDirectoryProvider
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.mail import GraphMailProvider
from pb_api.integrations.workspace.graph.notifications import GraphNotificationsProvider
from pb_api.integrations.workspace.graph.presence import GraphPresenceProvider
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver
from pb_api.integrations.workspace.graph.storage import GraphStorageProvider
from pb_api.integrations.workspace.graph.tasks import GraphTasksProvider
from pb_api.integrations.workspace.graph.teams import GraphTeamsProvider
from pb_api.integrations.workspace.ports.providers import (
    CalendarProvider,
    ContactsProvider,
    DirectoryProvider,
    MailProvider,
    MeetingProvider,
    NotificationProvider,
    PresenceProvider,
    StorageProvider,
    TaskProvider,
)

# Graph caps subscription lifetimes per resource; three days is a safe default when
# the caller supplies no explicit expiry (well under the message limit).
_DEFAULT_SUBSCRIPTION_TTL = timedelta(days=2, hours=23)


class GraphWorkspaceProvider:
    """Implements :class:`WorkspaceProvider` over Microsoft Graph."""

    def __init__(
        self,
        client: GraphClient,
        resolver: GraphResourceResolver,
        settings: WorkspaceSettings,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._settings = settings
        self._mail = GraphMailProvider(client, resolver)
        self._calendar = GraphCalendarProvider(client, resolver)
        self._contacts = GraphContactsProvider(client, resolver)
        self._directory = GraphDirectoryProvider(client, resolver)
        self._storage = GraphStorageProvider(client, resolver)
        self._teams = GraphTeamsProvider(client, resolver)
        self._presence = GraphPresenceProvider(client, resolver)
        self._notifications = GraphNotificationsProvider(client, resolver)
        self._tasks = GraphTasksProvider(client, resolver)

    @property
    def provider(self) -> Provider:
        return Provider.MICROSOFT_GRAPH

    @property
    def mail(self) -> MailProvider:
        return self._mail

    @property
    def calendar(self) -> CalendarProvider:
        return self._calendar

    @property
    def contacts(self) -> ContactsProvider:
        return self._contacts

    @property
    def directory(self) -> DirectoryProvider:
        return self._directory

    @property
    def storage(self) -> StorageProvider:
        return self._storage

    @property
    def meetings(self) -> MeetingProvider:
        return self._teams

    @property
    def presence(self) -> PresenceProvider:
        return self._presence

    @property
    def notifications(self) -> NotificationProvider:
        return self._notifications

    @property
    def tasks(self) -> TaskProvider:
        return self._tasks

    async def healthcheck(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> bool:
        try:
            mailbox = await self._resolver.mailbox(tenant_id, connection_id)
            await self._client.get(
                f"/users/{mailbox}",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params={"$select": "id"},
            )
        except GraphError:
            return await self._healthcheck_organization(tenant_id, connection_id)
        return True

    async def _healthcheck_organization(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> bool:
        try:
            await self._client.get(
                "/organization",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params={"$select": "id"},
            )
        except GraphError:
            return False
        return True

    async def create_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription:
        expires_at = subscription.expires_at or utcnow() + _DEFAULT_SUBSCRIPTION_TTL
        response = await self._client.post(
            "/subscriptions",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={
                "changeType": ",".join(subscription.change_types),
                "notificationUrl": subscription.notification_url,
                "resource": subscription.resource,
                "clientState": subscription.client_state,
                "expirationDateTime": to_graph_utc_iso(expires_at),
            },
        )
        body = response.json()
        return subscription.model_copy(
            update={
                "provider_subscription_id": str(body.get("id", "")),
                "expires_at": parse_graph_datetime(body.get("expirationDateTime")) or expires_at,
                "active": True,
            }
        )

    async def renew_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription:
        if not subscription.provider_subscription_id:
            raise GraphError(
                "cannot renew a subscription without a provider id",
                status_code=400,
                code="MissingSubscriptionId",
            )
        expires_at = subscription.expires_at or utcnow() + _DEFAULT_SUBSCRIPTION_TTL
        response = await self._client.patch(
            f"/subscriptions/{subscription.provider_subscription_id}",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"expirationDateTime": to_graph_utc_iso(expires_at)},
        )
        body = response.json()
        return subscription.model_copy(
            update={
                "expires_at": parse_graph_datetime(body.get("expirationDateTime")) or expires_at,
                "active": True,
            }
        )

    async def delete_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, provider_subscription_id: str
    ) -> None:
        await self._client.delete(
            f"/subscriptions/{provider_subscription_id}",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
