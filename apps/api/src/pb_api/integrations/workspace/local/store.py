"""In-memory data store backing the local workspace adapter.

The store is a tenant- and connection-keyed collection of the workspace domain
objects (messages, events, contacts, directory users/groups, drive items, sites,
tasks, Teams channels/messages, presence, notifications, webhook subscriptions,
and indexed documents). It is deliberately provider-agnostic and holds no I/O: it
is the persistence layer of a first-class alternate backend (mirroring the way
``MemoryRateLimiter`` is a real alternative to ``RedisRateLimiter``), used for
development, air-gapped operation, and tests.

Two mechanisms make delta synchronization real rather than stubbed:

* every delta-tracked resource carries a monotonically increasing version counter
  (:class:`ResourceVersion`); each create/update stamps the changed object with
  the counter's new value, and
* deletions are recorded as tombstones so a delta sweep can report ``removed_ids``.

Seeding helpers let tests populate a mailbox/calendar/etc. before exercising a
provider.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TypeVar
from uuid import uuid4

from pb_api.integrations.workspace.domain.calendar import CalendarEvent
from pb_api.integrations.workspace.domain.common import SyncResource
from pb_api.integrations.workspace.domain.contacts import WorkspaceContact
from pb_api.integrations.workspace.domain.directory import DirectoryGroup, DirectoryUser
from pb_api.integrations.workspace.domain.files import (
    DriveItem,
    IndexedDocument,
    SharePointSite,
)
from pb_api.integrations.workspace.domain.mail import Attachment, DraftReply, WorkspaceMessage
from pb_api.integrations.workspace.domain.presence import Notification, Presence
from pb_api.integrations.workspace.domain.sync import WebhookSubscription
from pb_api.integrations.workspace.domain.tasks import WorkspaceTask
from pb_api.integrations.workspace.domain.teams import TeamsChannel, TeamsMessage

_V = TypeVar("_V")


def new_provider_id() -> str:
    """Mint a provider-style identifier, e.g. ``mem-1f3c...`` (vendor-opaque)."""
    return f"mem-{uuid4().hex}"


def _empty_versions() -> dict[SyncResource, ResourceVersion]:
    return {resource: ResourceVersion() for resource in SyncResource}


@dataclass(slots=True)
class ResourceVersion:
    """A monotonic change log for one delta-tracked resource of one connection.

    ``version`` only ever increases. ``changed_at`` maps a live object's provider
    id to the version at which it last changed; ``tombstones`` maps a deleted
    object's provider id to the version at which it was removed. A delta sweep that
    arrives with a token ``V`` returns objects whose ``changed_at`` exceeds ``V``
    and tombstones whose version exceeds ``V``.
    """

    version: int = 0
    changed_at: dict[str, int] = field(default_factory=dict)
    tombstones: dict[str, int] = field(default_factory=dict)

    def bump(self, provider_id: str) -> None:
        """Record a create/update: advance the counter and stamp the object."""
        self.version += 1
        self.changed_at[provider_id] = self.version
        self.tombstones.pop(provider_id, None)

    def remove(self, provider_id: str) -> None:
        """Record a deletion: advance the counter and write a tombstone."""
        self.version += 1
        self.changed_at.pop(provider_id, None)
        self.tombstones[provider_id] = self.version


@dataclass(slots=True)
class ConnectionData:
    """All workspace data for a single ``(tenant_id, connection_id)`` pair.

    Objects are keyed by their provider id so lookups, updates, and deletions are
    O(1); the insertion order of each mapping gives paginated listings a stable,
    deterministic order.
    """

    messages: dict[str, WorkspaceMessage] = field(default_factory=dict)
    drafts: dict[str, DraftReply] = field(default_factory=dict)
    attachment_bytes: dict[tuple[str, str], bytes] = field(default_factory=dict)
    events: dict[str, CalendarEvent] = field(default_factory=dict)
    contacts: dict[str, WorkspaceContact] = field(default_factory=dict)
    users: dict[str, DirectoryUser] = field(default_factory=dict)
    groups: dict[str, DirectoryGroup] = field(default_factory=dict)
    sites: dict[str, SharePointSite] = field(default_factory=dict)
    drive_items: dict[str, DriveItem] = field(default_factory=dict)
    drive_content: dict[str, bytes] = field(default_factory=dict)
    tasks: dict[str, WorkspaceTask] = field(default_factory=dict)
    channels: dict[str, TeamsChannel] = field(default_factory=dict)
    teams_messages: dict[str, TeamsMessage] = field(default_factory=dict)
    presence: dict[str, Presence] = field(default_factory=dict)
    notifications: dict[str, Notification] = field(default_factory=dict)
    subscriptions: dict[str, WebhookSubscription] = field(default_factory=dict)
    indexed_docs: list[IndexedDocument] = field(default_factory=list)
    versions: dict[SyncResource, ResourceVersion] = field(default_factory=_empty_versions)

    def touch(self, resource: SyncResource, provider_id: str) -> None:
        """Stamp a create/update against ``resource``'s change log."""
        self.versions[resource].bump(provider_id)


class InMemoryStore:
    """A process-local store keyed by ``(tenant_id, connection_id)``.

    Instantiate one store and share it across the provider classes (they all read
    and write the same connection buckets). Tests seed data through the
    ``seed_*`` helpers; providers mutate through the typed mappings and record
    versions via :meth:`ConnectionData.touch` and :meth:`delete_*`.
    """

    def __init__(self) -> None:
        self._connections: dict[tuple[uuid.UUID, uuid.UUID], ConnectionData] = {}

    def connection(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> ConnectionData:
        """Return the bucket for a connection, creating an empty one on first use."""
        return self._connections.setdefault((tenant_id, connection_id), ConnectionData())

    # -- deletion (records tombstones for delta sync) --------------------------

    @staticmethod
    def _remove(
        conn: ConnectionData,
        resource: SyncResource,
        table: dict[str, _V],
        provider_id: str,
    ) -> bool:
        if table.pop(provider_id, None) is None:
            return False
        conn.versions[resource].remove(provider_id)
        return True

    def delete_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> bool:
        """Delete a message and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.MAIL, conn.messages, message_provider_id)

    def delete_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event_provider_id: str
    ) -> bool:
        """Delete a calendar event and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.CALENDAR, conn.events, event_provider_id)

    def delete_contact(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, contact_provider_id: str
    ) -> bool:
        """Delete a contact and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.CONTACTS, conn.contacts, contact_provider_id)

    def delete_user(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, user_provider_id: str
    ) -> bool:
        """Delete a directory user and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.DIRECTORY_USERS, conn.users, user_provider_id)

    def delete_group(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, group_provider_id: str
    ) -> bool:
        """Delete a directory group and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.DIRECTORY_GROUPS, conn.groups, group_provider_id)

    def delete_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task_provider_id: str
    ) -> bool:
        """Delete a task and tombstone it; return whether it existed."""
        conn = self.connection(tenant_id, connection_id)
        return self._remove(conn, SyncResource.TASKS, conn.tasks, task_provider_id)

    def delete_drive_item(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, item_provider_id: str
    ) -> bool:
        """Delete a drive item (and its bytes) and tombstone it."""
        conn = self.connection(tenant_id, connection_id)
        conn.drive_content.pop(item_provider_id, None)
        return self._remove(conn, SyncResource.FILES, conn.drive_items, item_provider_id)

    # -- seeding ---------------------------------------------------------------

    def seed_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        messages: Iterable[WorkspaceMessage],
    ) -> None:
        """Populate a mailbox; each message is (re)stamped with ``tenant_id``."""
        conn = self.connection(tenant_id, connection_id)
        for message in messages:
            stored = message.model_copy(update={"tenant_id": tenant_id})
            conn.messages[stored.provider_id] = stored
            conn.touch(SyncResource.MAIL, stored.provider_id)

    def seed_attachment(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        attachment: Attachment,
        content: bytes = b"",
    ) -> None:
        """Attach metadata + bytes to a stored message so download/list work."""
        conn = self.connection(tenant_id, connection_id)
        message = conn.messages.get(message_provider_id)
        if message is not None:
            message.attachments.append(attachment)
            message.has_attachments = True
        conn.attachment_bytes[message_provider_id, attachment.id] = content

    def seed_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        events: Iterable[CalendarEvent],
    ) -> None:
        """Populate a calendar; events without a provider id are assigned one."""
        conn = self.connection(tenant_id, connection_id)
        for event in events:
            provider_id = event.provider_id or new_provider_id()
            stored = event.model_copy(update={"tenant_id": tenant_id, "provider_id": provider_id})
            conn.events[provider_id] = stored
            conn.touch(SyncResource.CALENDAR, provider_id)

    def seed_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        contacts: Iterable[WorkspaceContact],
    ) -> None:
        """Populate the contacts store."""
        conn = self.connection(tenant_id, connection_id)
        for contact in contacts:
            stored = contact.model_copy(update={"tenant_id": tenant_id})
            conn.contacts[stored.provider_id] = stored
            conn.touch(SyncResource.CONTACTS, stored.provider_id)

    def seed_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        users: Iterable[DirectoryUser],
    ) -> None:
        """Populate the directory's users."""
        conn = self.connection(tenant_id, connection_id)
        for user in users:
            stored = user.model_copy(update={"tenant_id": tenant_id})
            conn.users[stored.provider_id] = stored
            conn.touch(SyncResource.DIRECTORY_USERS, stored.provider_id)

    def seed_groups(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        groups: Iterable[DirectoryGroup],
    ) -> None:
        """Populate the directory's groups."""
        conn = self.connection(tenant_id, connection_id)
        for group in groups:
            stored = group.model_copy(update={"tenant_id": tenant_id})
            conn.groups[stored.provider_id] = stored
            conn.touch(SyncResource.DIRECTORY_GROUPS, stored.provider_id)

    def seed_sites(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        sites: Iterable[SharePointSite],
    ) -> None:
        """Populate the SharePoint sites list."""
        conn = self.connection(tenant_id, connection_id)
        for site in sites:
            stored = site.model_copy(update={"tenant_id": tenant_id})
            conn.sites[stored.provider_id] = stored

    def seed_drive_items(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        items: Iterable[DriveItem],
    ) -> None:
        """Populate drive item metadata (bytes via :meth:`seed_drive_content`)."""
        conn = self.connection(tenant_id, connection_id)
        for item in items:
            stored = item.model_copy(update={"tenant_id": tenant_id})
            conn.drive_items[stored.provider_id] = stored
            conn.touch(SyncResource.FILES, stored.provider_id)

    def seed_drive_content(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        item_provider_id: str,
        content: bytes,
    ) -> None:
        """Attach downloadable bytes to a drive item."""
        conn = self.connection(tenant_id, connection_id)
        conn.drive_content[item_provider_id] = content

    def seed_tasks(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        tasks: Iterable[WorkspaceTask],
    ) -> None:
        """Populate the tasks store."""
        conn = self.connection(tenant_id, connection_id)
        for task in tasks:
            stored = task.model_copy(update={"tenant_id": tenant_id})
            conn.tasks[stored.provider_id] = stored
            conn.touch(SyncResource.TASKS, stored.provider_id)

    def seed_channels(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        channels: Iterable[TeamsChannel],
    ) -> None:
        """Populate Teams channels."""
        conn = self.connection(tenant_id, connection_id)
        for channel in channels:
            stored = channel.model_copy(update={"tenant_id": tenant_id})
            conn.channels[stored.provider_id] = stored

    def seed_teams_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        messages: Iterable[TeamsMessage],
    ) -> None:
        """Populate Teams channel/chat messages."""
        conn = self.connection(tenant_id, connection_id)
        for message in messages:
            stored = message.model_copy(update={"tenant_id": tenant_id})
            conn.teams_messages[stored.provider_id] = stored

    def seed_presence(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        presences: Iterable[Presence],
    ) -> None:
        """Populate presence records keyed by user provider id."""
        conn = self.connection(tenant_id, connection_id)
        for presence in presences:
            stored = presence.model_copy(update={"tenant_id": tenant_id})
            conn.presence[stored.user_provider_id] = stored

    def seed_indexed_documents(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        documents: Iterable[IndexedDocument],
    ) -> None:
        """Populate the knowledge index."""
        conn = self.connection(tenant_id, connection_id)
        for document in documents:
            conn.indexed_docs.append(document.model_copy(update={"tenant_id": tenant_id}))
