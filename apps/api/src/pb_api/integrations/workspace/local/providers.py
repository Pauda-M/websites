"""In-memory provider adapters implementing the workspace ports.

Each class here is a concrete, fully-functional implementation of one port from
``ports/providers.py`` backed by an :class:`InMemoryStore`; together they compose
into :class:`InMemoryWorkspaceProvider`, the aggregate that satisfies
``WorkspaceProvider``. This is a first-class alternate backend — not a mock —
used for development, air-gapped operation, and tests.

Encoding conventions (identical across every listing/delta method):

* **Cursor pagination** — the opaque ``cursor`` string is a decimal integer
  offset into the current, deterministically ordered result set. A page returns
  ``next_cursor = str(offset + page_size)`` while more remain, else ``None``.
* **Delta tokens** — the ``delta_token`` string is the last-seen value of the
  resource's monotonic version counter. A sweep with token ``V`` yields objects
  changed after ``V`` (walking pages via ``next_cursor``) plus tombstoned
  ``removed_ids``; the final page carries ``delta_token = str(current_version)``
  and ``next_cursor = None``. A first sweep (no token) returns everything and no
  removals.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, TypeVar

from pb_api.integrations.workspace.domain.calendar import (
    AttendeeResponse,
    AvailabilitySlot,
    CalendarEvent,
    TimeSlot,
)
from pb_api.integrations.workspace.domain.common import (
    Provider,
    SyncResource,
    ensure_aware,
    utcnow,
)
from pb_api.integrations.workspace.domain.contacts import WorkspaceContact
from pb_api.integrations.workspace.domain.directory import DirectoryGroup, DirectoryUser
from pb_api.integrations.workspace.domain.files import DriveItem, SharePointSite
from pb_api.integrations.workspace.domain.mail import (
    Attachment,
    DraftReply,
    EmailAddress,
    WorkspaceMessage,
)
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.domain.presence import Availability, Notification, Presence
from pb_api.integrations.workspace.domain.sync import WebhookSubscription
from pb_api.integrations.workspace.domain.tasks import WorkspaceTask, WorkspaceTaskStatus
from pb_api.integrations.workspace.domain.teams import TeamsChannel, TeamsMessage
from pb_api.integrations.workspace.local.store import (
    ConnectionData,
    InMemoryStore,
    ResourceVersion,
    new_provider_id,
)

if TYPE_CHECKING:
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
        WorkspaceProvider,
    )

_T = TypeVar("_T")

_DELTA_PAGE_SIZE = 50
"""Page size used to walk a delta sweep (the delta ports take no ``page_size``)."""

_PREVIEW_CHARS = 255
"""How much of a sent message's body is retained as its ``body_preview``."""

_SUBSCRIPTION_TTL = timedelta(days=3)
"""How far into the future a created/renewed webhook subscription expires."""

_DEFAULT_SELF_ADDRESS = "me@in-memory.local"
"""The mailbox owner's address, used as the sender of sent mail and to match the
current user when responding to a calendar invitation. Overridable per provider."""

_RESPONSE_ALIASES: dict[str, AttendeeResponse] = {
    "accept": AttendeeResponse.ACCEPTED,
    "accepted": AttendeeResponse.ACCEPTED,
    "tentative": AttendeeResponse.TENTATIVE,
    "tentativelyaccept": AttendeeResponse.TENTATIVE,
    "tentativelyaccepted": AttendeeResponse.TENTATIVE,
    "decline": AttendeeResponse.DECLINED,
    "declined": AttendeeResponse.DECLINED,
    "none": AttendeeResponse.NONE,
}


def _decode_offset(cursor: str | None) -> int:
    """Decode a cursor/token into a non-negative integer offset (default 0)."""
    if cursor is None:
        return 0
    try:
        return max(int(cursor), 0)
    except ValueError:
        return 0


def _paginate(items: Sequence[_T], cursor: str | None, page_size: int) -> Page[_T]:
    """Slice ``items`` at ``cursor`` and encode the next offset as ``next_cursor``."""
    size = max(page_size, 1)
    offset = _decode_offset(cursor)
    window = list(items[offset : offset + size])
    next_offset = offset + size
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return Page(items=window, next_cursor=next_cursor)


def _delta(
    versioned: ResourceVersion,
    items_by_id: Mapping[str, _T],
    *,
    delta_token: str | None,
    cursor: str | None,
) -> DeltaPage[_T]:
    """Return one page of a delta sweep for a versioned resource.

    Objects whose change version exceeds the token are returned in change order;
    the sweep is walked by ``next_cursor`` and closed on the final page with the
    current version as ``delta_token`` plus any tombstoned ``removed_ids`` (a
    first sweep, i.e. no token, reports no removals).
    """
    since = _decode_offset(delta_token)
    first_sweep = delta_token is None
    changed_ids = sorted(
        (pid for pid, ver in versioned.changed_at.items() if ver > since and pid in items_by_id),
        key=lambda pid: versioned.changed_at[pid],
    )
    offset = _decode_offset(cursor)
    window = [items_by_id[pid] for pid in changed_ids[offset : offset + _DELTA_PAGE_SIZE]]
    next_offset = offset + _DELTA_PAGE_SIZE
    if next_offset < len(changed_ids):
        return DeltaPage(items=window, next_cursor=str(next_offset))
    removed_ids: tuple[str, ...] = (
        ()
        if first_sweep
        else tuple(pid for pid, ver in versioned.tombstones.items() if ver > since)
    )
    return DeltaPage(
        items=window,
        next_cursor=None,
        delta_token=str(versioned.version),
        removed_ids=removed_ids,
    )


def _parse_response(response: str) -> AttendeeResponse:
    """Map a free-form response verb to an :class:`AttendeeResponse`."""
    return _RESPONSE_ALIASES.get(response.strip().lower(), AttendeeResponse.NONE)


class InMemoryMailProvider:
    """In-memory :class:`MailProvider` over a mailbox in the store."""

    def __init__(self, store: InMemoryStore, *, self_address: str = _DEFAULT_SELF_ADDRESS) -> None:
        self._store = store
        self._self_address = self_address

    @staticmethod
    def _require(conn: ConnectionData, message_provider_id: str) -> WorkspaceMessage:
        message = conn.messages.get(message_provider_id)
        if message is None:
            raise KeyError(f"unknown message: {message_provider_id!r}")
        return message

    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        folder: str = "inbox",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]:
        conn = self._store.connection(tenant_id, connection_id)
        items = [message for message in conn.messages.values() if message.folder == folder]
        return _paginate(items, cursor, page_size)

    async def delta_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceMessage]:
        conn = self._store.connection(tenant_id, connection_id)
        return _delta(
            conn.versions[SyncResource.MAIL],
            conn.messages,
            delta_token=delta_token,
            cursor=cursor,
        )

    async def get_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> WorkspaceMessage | None:
        conn = self._store.connection(tenant_id, connection_id)
        return conn.messages.get(message_provider_id)

    async def get_attachments(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> list[Attachment]:
        conn = self._store.connection(tenant_id, connection_id)
        message = conn.messages.get(message_provider_id)
        return list(message.attachments) if message is not None else []

    async def download_attachment(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        attachment_id: str,
    ) -> bytes:
        conn = self._store.connection(tenant_id, connection_id)
        return conn.attachment_bytes.get((message_provider_id, attachment_id), b"")

    async def create_draft(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply
    ) -> DraftReply:
        conn = self._store.connection(tenant_id, connection_id)
        provider_draft_id = draft.provider_draft_id or new_provider_id()
        stored = draft.model_copy(
            update={"tenant_id": tenant_id, "provider_draft_id": provider_draft_id}
        )
        conn.drafts[provider_draft_id] = stored
        return stored

    async def send(self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = new_provider_id()
        message = WorkspaceMessage(
            tenant_id=tenant_id,
            provider_id=provider_id,
            conversation_id=draft.conversation_id,
            subject=draft.subject,
            body=draft.body,
            body_preview=draft.body[:_PREVIEW_CHARS],
            is_html=draft.is_html,
            sender=EmailAddress(address=self._self_address),
            to=list(draft.to),
            cc=list(draft.cc),
            received_at=utcnow(),
            is_read=True,
            folder="sentitems",
        )
        conn.messages[provider_id] = message
        conn.touch(SyncResource.MAIL, provider_id)
        if draft.provider_draft_id is not None:
            conn.drafts.pop(draft.provider_draft_id, None)
        return provider_id

    async def move(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        destination_folder: str,
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        message = self._require(conn, message_provider_id)
        conn.messages[message_provider_id] = message.model_copy(
            update={"folder": destination_folder}
        )
        conn.touch(SyncResource.MAIL, message_provider_id)

    async def set_categories(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        categories: list[str],
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        message = self._require(conn, message_provider_id)
        conn.messages[message_provider_id] = message.model_copy(
            update={"categories": list(categories)}
        )
        conn.touch(SyncResource.MAIL, message_provider_id)

    async def set_flag(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        flagged: bool,
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        message = self._require(conn, message_provider_id)
        conn.messages[message_provider_id] = message.model_copy(update={"is_flagged": flagged})
        conn.touch(SyncResource.MAIL, message_provider_id)

    async def set_read(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        is_read: bool,
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        message = self._require(conn, message_provider_id)
        conn.messages[message_provider_id] = message.model_copy(update={"is_read": is_read})
        conn.touch(SyncResource.MAIL, message_provider_id)

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]:
        conn = self._store.connection(tenant_id, connection_id)
        needle = query.lower()
        items = [
            message for message in conn.messages.values() if needle in _message_haystack(message)
        ]
        return _paginate(items, cursor, page_size)


def _message_haystack(message: WorkspaceMessage) -> str:
    parts = (
        message.subject,
        message.body,
        message.body_preview,
        message.sender.address,
        message.sender.name,
    )
    return " ".join(parts).lower()


class InMemoryCalendarProvider:
    """In-memory :class:`CalendarProvider` over a connection's events."""

    def __init__(self, store: InMemoryStore, *, self_address: str = _DEFAULT_SELF_ADDRESS) -> None:
        self._store = store
        self._self_address = self_address

    @staticmethod
    def _require(conn: ConnectionData, event_provider_id: str) -> CalendarEvent:
        event = conn.events.get(event_provider_id)
        if event is None:
            raise KeyError(f"unknown event: {event_provider_id!r}")
        return event

    async def list_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[CalendarEvent]:
        conn = self._store.connection(tenant_id, connection_id)
        return _paginate(list(conn.events.values()), cursor, page_size)

    async def delta_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[CalendarEvent]:
        conn = self._store.connection(tenant_id, connection_id)
        return _delta(
            conn.versions[SyncResource.CALENDAR],
            conn.events,
            delta_token=delta_token,
            cursor=cursor,
        )

    async def create_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = event.provider_id or new_provider_id()
        conn.events[provider_id] = event.model_copy(
            update={"tenant_id": tenant_id, "provider_id": provider_id}
        )
        conn.touch(SyncResource.CALENDAR, provider_id)
        return provider_id

    async def update_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = event.provider_id
        if provider_id is None:
            raise ValueError("update_event requires event.provider_id")
        if provider_id not in conn.events:
            raise KeyError(f"unknown event: {provider_id!r}")
        conn.events[provider_id] = event.model_copy(update={"tenant_id": tenant_id})
        conn.touch(SyncResource.CALENDAR, provider_id)

    async def cancel_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event_provider_id: str
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        event = self._require(conn, event_provider_id)
        conn.events[event_provider_id] = event.model_copy(update={"is_cancelled": True})
        conn.touch(SyncResource.CALENDAR, event_provider_id)

    async def respond(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        event_provider_id: str,
        response: str,
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        event = self._require(conn, event_provider_id)
        decision = _parse_response(response)
        self_address = self._self_address.lower()
        attendees = [
            (
                attendee.model_copy(update={"response": decision})
                if attendee.email.address.lower() == self_address
                else attendee
            )
            for attendee in event.attendees
        ]
        conn.events[event_provider_id] = event.model_copy(update={"attendees": attendees})
        conn.touch(SyncResource.CALENDAR, event_provider_id)

    async def availability(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        attendee_provider_ids: list[str],
        window_start: datetime,
        window_end: datetime,
        slot_minutes: int = 30,
    ) -> list[AvailabilitySlot]:
        conn = self._store.connection(tenant_id, connection_id)
        start = ensure_aware(window_start)
        end = ensure_aware(window_end)
        step = timedelta(minutes=max(slot_minutes, 1))
        busy = [
            (ensure_aware(event.start), ensure_aware(event.end))
            for event in conn.events.values()
            if not event.is_cancelled
        ]
        slots: list[AvailabilitySlot] = []
        moment = start
        while moment < end:
            slot_end = min(moment + step, end)
            overlaps = any(
                busy_start < slot_end and busy_end > moment for busy_start, busy_end in busy
            )
            slots.append(
                AvailabilitySlot(
                    slot=TimeSlot(start=moment, end=slot_end),
                    free_attendees=[] if overlaps else list(attendee_provider_ids),
                    all_free=not overlaps,
                )
            )
            moment = slot_end
        return slots


class InMemoryContactsProvider:
    """In-memory :class:`ContactsProvider`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceContact]:
        conn = self._store.connection(tenant_id, connection_id)
        return _paginate(list(conn.contacts.values()), cursor, page_size)

    async def delta_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceContact]:
        conn = self._store.connection(tenant_id, connection_id)
        return _delta(
            conn.versions[SyncResource.CONTACTS],
            conn.contacts,
            delta_token=delta_token,
            cursor=cursor,
        )

    async def upsert_contact(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, contact: WorkspaceContact
    ) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = contact.provider_id or new_provider_id()
        conn.contacts[provider_id] = contact.model_copy(
            update={"tenant_id": tenant_id, "provider_id": provider_id}
        )
        conn.touch(SyncResource.CONTACTS, provider_id)
        return provider_id


class InMemoryDirectoryProvider:
    """In-memory :class:`DirectoryProvider`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryUser]:
        conn = self._store.connection(tenant_id, connection_id)
        return _paginate(list(conn.users.values()), cursor, page_size)

    async def delta_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[DirectoryUser]:
        conn = self._store.connection(tenant_id, connection_id)
        return _delta(
            conn.versions[SyncResource.DIRECTORY_USERS],
            conn.users,
            delta_token=delta_token,
            cursor=cursor,
        )

    async def list_groups(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryGroup]:
        conn = self._store.connection(tenant_id, connection_id)
        return _paginate(list(conn.groups.values()), cursor, page_size)

    async def get_user(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, user_provider_id: str
    ) -> DirectoryUser | None:
        conn = self._store.connection(tenant_id, connection_id)
        return conn.users.get(user_provider_id)


class InMemoryStorageProvider:
    """In-memory :class:`StorageProvider` (SharePoint sites + drive items)."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_sites(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> list[SharePointSite]:
        conn = self._store.connection(tenant_id, connection_id)
        return list(conn.sites.values())

    async def list_items(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DriveItem]:
        conn = self._store.connection(tenant_id, connection_id)
        items = [item for item in conn.drive_items.values() if item.drive_id == drive_id]
        return _paginate(items, cursor, page_size)

    async def download(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        item_provider_id: str,
    ) -> bytes:
        conn = self._store.connection(tenant_id, connection_id)
        return conn.drive_content.get(item_provider_id, b"")

    async def upload(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DriveItem:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = new_provider_id()
        pure = PurePosixPath(path)
        parent = str(pure.parent)
        item = DriveItem(
            tenant_id=tenant_id,
            provider_id=provider_id,
            drive_id=drive_id,
            name=pure.name or path,
            content_type=content_type,
            size_bytes=len(content),
            parent_path=parent if parent not in (".", "") else "/",
        )
        conn.drive_items[provider_id] = item
        conn.drive_content[provider_id] = content
        conn.touch(SyncResource.FILES, provider_id)
        return item

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
    ) -> Page[DriveItem]:
        conn = self._store.connection(tenant_id, connection_id)
        needle = query.lower()
        items = [
            item
            for item in conn.drive_items.values()
            if needle in f"{item.name} {item.parent_path}".lower()
        ]
        return _paginate(items, cursor, _DELTA_PAGE_SIZE)


class InMemoryMeetingProvider:
    """In-memory :class:`MeetingProvider` (Teams channels + messages)."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_channels(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, team_provider_id: str
    ) -> list[TeamsChannel]:
        conn = self._store.connection(tenant_id, connection_id)
        return [
            channel
            for channel in conn.channels.values()
            if channel.team_provider_id == team_provider_id
        ]

    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        conversation_provider_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[TeamsMessage]:
        conn = self._store.connection(tenant_id, connection_id)
        items = [
            message
            for message in conn.teams_messages.values()
            if message.conversation_provider_id == conversation_provider_id
        ]
        return _paginate(items, cursor, page_size)

    async def post_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message: TeamsMessage
    ) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = new_provider_id()
        conn.teams_messages[provider_id] = message.model_copy(
            update={"tenant_id": tenant_id, "provider_id": provider_id}
        )
        return provider_id


class InMemoryPresenceProvider:
    """In-memory :class:`PresenceProvider`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get_presence(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, user_provider_ids: list[str]
    ) -> list[Presence]:
        conn = self._store.connection(tenant_id, connection_id)
        return [
            conn.presence.get(
                user_provider_id,
                Presence(
                    tenant_id=tenant_id,
                    user_provider_id=user_provider_id,
                    availability=Availability.UNKNOWN,
                ),
            )
            for user_provider_id in user_provider_ids
        ]


class InMemoryNotificationProvider:
    """In-memory :class:`NotificationProvider`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def send(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, notification: Notification
    ) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        stored = notification.model_copy(update={"tenant_id": tenant_id})
        notification_id = str(stored.id)
        conn.notifications[notification_id] = stored
        return notification_id


class InMemoryTaskProvider:
    """In-memory :class:`TaskProvider` (To Do / Planner tasks)."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        source: str = "todo",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceTask]:
        conn = self._store.connection(tenant_id, connection_id)
        items = [task for task in conn.tasks.values() if task.source == source]
        return _paginate(items, cursor, page_size)

    async def create_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task: WorkspaceTask
    ) -> str:
        conn = self._store.connection(tenant_id, connection_id)
        provider_id = task.provider_id or new_provider_id()
        conn.tasks[provider_id] = task.model_copy(
            update={"tenant_id": tenant_id, "provider_id": provider_id}
        )
        conn.touch(SyncResource.TASKS, provider_id)
        return provider_id

    async def complete_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task_provider_id: str
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        task = conn.tasks.get(task_provider_id)
        if task is None:
            raise KeyError(f"unknown task: {task_provider_id!r}")
        now = utcnow()
        conn.tasks[task_provider_id] = task.model_copy(
            update={
                "status": WorkspaceTaskStatus.COMPLETED,
                "completed_at": now,
                "updated_at": now,
            }
        )
        conn.touch(SyncResource.TASKS, task_provider_id)


class InMemoryWorkspaceProvider:
    """The aggregate in-memory adapter satisfying ``WorkspaceProvider``.

    Compose one over a shared :class:`InMemoryStore` (created for you if omitted)
    and reach every capability through the ``mail``/``calendar``/… properties.
    Webhook subscriptions are stored per connection with a rolling expiry, and
    ``healthcheck`` always reports reachable.
    """

    def __init__(
        self,
        store: InMemoryStore | None = None,
        *,
        self_address: str = _DEFAULT_SELF_ADDRESS,
    ) -> None:
        self._store = store if store is not None else InMemoryStore()
        self._mail = InMemoryMailProvider(self._store, self_address=self_address)
        self._calendar = InMemoryCalendarProvider(self._store, self_address=self_address)
        self._contacts = InMemoryContactsProvider(self._store)
        self._directory = InMemoryDirectoryProvider(self._store)
        self._storage = InMemoryStorageProvider(self._store)
        self._meetings = InMemoryMeetingProvider(self._store)
        self._presence = InMemoryPresenceProvider(self._store)
        self._notifications = InMemoryNotificationProvider(self._store)
        self._tasks = InMemoryTaskProvider(self._store)

    @property
    def store(self) -> InMemoryStore:
        """The backing store — seed it in tests before exercising the providers."""
        return self._store

    @property
    def provider(self) -> Provider:
        return Provider.IN_MEMORY

    @property
    def mail(self) -> InMemoryMailProvider:
        return self._mail

    @property
    def calendar(self) -> InMemoryCalendarProvider:
        return self._calendar

    @property
    def contacts(self) -> InMemoryContactsProvider:
        return self._contacts

    @property
    def directory(self) -> InMemoryDirectoryProvider:
        return self._directory

    @property
    def storage(self) -> InMemoryStorageProvider:
        return self._storage

    @property
    def meetings(self) -> InMemoryMeetingProvider:
        return self._meetings

    @property
    def presence(self) -> InMemoryPresenceProvider:
        return self._presence

    @property
    def notifications(self) -> InMemoryNotificationProvider:
        return self._notifications

    @property
    def tasks(self) -> InMemoryTaskProvider:
        return self._tasks

    async def healthcheck(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> bool:
        return True

    async def create_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription:
        conn = self._store.connection(tenant_id, connection_id)
        provider_subscription_id = subscription.provider_subscription_id or new_provider_id()
        stored = subscription.model_copy(
            update={
                "tenant_id": tenant_id,
                "connection_id": connection_id,
                "provider": Provider.IN_MEMORY,
                "provider_subscription_id": provider_subscription_id,
                "expires_at": utcnow() + _SUBSCRIPTION_TTL,
                "active": True,
            }
        )
        conn.subscriptions[provider_subscription_id] = stored
        return stored

    async def renew_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription:
        conn = self._store.connection(tenant_id, connection_id)
        provider_subscription_id = subscription.provider_subscription_id
        if provider_subscription_id is None:
            raise ValueError("renew_subscription requires subscription.provider_subscription_id")
        base = conn.subscriptions.get(provider_subscription_id, subscription)
        renewed = base.model_copy(
            update={
                "tenant_id": tenant_id,
                "connection_id": connection_id,
                "provider": Provider.IN_MEMORY,
                "provider_subscription_id": provider_subscription_id,
                "expires_at": utcnow() + _SUBSCRIPTION_TTL,
                "active": True,
            }
        )
        conn.subscriptions[provider_subscription_id] = renewed
        return renewed

    async def delete_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, provider_subscription_id: str
    ) -> None:
        conn = self._store.connection(tenant_id, connection_id)
        conn.subscriptions.pop(provider_subscription_id, None)


if TYPE_CHECKING:
    # Structural conformance guard: this fails to type-check if any adapter above
    # drifts from the exact signature of the port it implements.
    def _assert_port_conformance(
        _mail: MailProvider,
        _calendar: CalendarProvider,
        _contacts: ContactsProvider,
        _directory: DirectoryProvider,
        _storage: StorageProvider,
        _meetings: MeetingProvider,
        _presence: PresenceProvider,
        _notifications: NotificationProvider,
        _tasks: TaskProvider,
        _workspace: WorkspaceProvider,
    ) -> None: ...

    _conformance_store = InMemoryStore()
    _assert_port_conformance(
        InMemoryMailProvider(_conformance_store),
        InMemoryCalendarProvider(_conformance_store),
        InMemoryContactsProvider(_conformance_store),
        InMemoryDirectoryProvider(_conformance_store),
        InMemoryStorageProvider(_conformance_store),
        InMemoryMeetingProvider(_conformance_store),
        InMemoryPresenceProvider(_conformance_store),
        InMemoryNotificationProvider(_conformance_store),
        InMemoryTaskProvider(_conformance_store),
        InMemoryWorkspaceProvider(_conformance_store),
    )
