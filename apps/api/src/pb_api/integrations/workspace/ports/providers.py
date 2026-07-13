"""Provider ports — the interfaces business logic depends on.

**Business logic MUST NEVER depend directly on Microsoft Graph.** It depends on
these Protocols; adapters (``graph/``, ``local/``) implement them. Adding a new
provider (Google Workspace, etc.) means implementing these Protocols and nothing
else — no business-logic change. All methods are tenant- and connection-scoped and
return provider-agnostic domain models plus ``Page``/``DeltaPage`` containers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from pb_api.integrations.workspace.domain.calendar import (
    AvailabilitySlot,
    CalendarEvent,
)
from pb_api.integrations.workspace.domain.common import Provider
from pb_api.integrations.workspace.domain.contacts import WorkspaceContact
from pb_api.integrations.workspace.domain.directory import DirectoryGroup, DirectoryUser
from pb_api.integrations.workspace.domain.files import DriveItem, SharePointSite
from pb_api.integrations.workspace.domain.mail import Attachment, DraftReply, WorkspaceMessage
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.domain.presence import Notification, Presence
from pb_api.integrations.workspace.domain.sync import WebhookSubscription
from pb_api.integrations.workspace.domain.tasks import WorkspaceTask
from pb_api.integrations.workspace.domain.teams import TeamsChannel, TeamsMessage


@runtime_checkable
class MailProvider(Protocol):
    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        folder: str = "inbox",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]: ...

    async def delta_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceMessage]: ...

    async def get_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> WorkspaceMessage | None: ...

    async def get_attachments(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> list[Attachment]: ...

    async def download_attachment(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        attachment_id: str,
    ) -> bytes: ...

    async def create_draft(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply
    ) -> DraftReply: ...

    async def send(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply
    ) -> str: ...

    async def move(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        destination_folder: str,
    ) -> None: ...

    async def set_categories(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        categories: list[str],
    ) -> None: ...

    async def set_flag(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        flagged: bool,
    ) -> None: ...

    async def set_read(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        is_read: bool,
    ) -> None: ...

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]: ...


@runtime_checkable
class CalendarProvider(Protocol):
    async def list_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[CalendarEvent]: ...

    async def delta_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[CalendarEvent]: ...

    async def create_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> str: ...

    async def update_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> None: ...

    async def cancel_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event_provider_id: str
    ) -> None: ...

    async def respond(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        event_provider_id: str,
        response: str,
    ) -> None: ...

    async def availability(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        attendee_provider_ids: list[str],
        window_start: datetime,
        window_end: datetime,
        slot_minutes: int = 30,
    ) -> list[AvailabilitySlot]: ...


@runtime_checkable
class ContactsProvider(Protocol):
    async def list_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceContact]: ...

    async def delta_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceContact]: ...

    async def upsert_contact(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, contact: WorkspaceContact
    ) -> str: ...


@runtime_checkable
class DirectoryProvider(Protocol):
    async def list_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryUser]: ...

    async def delta_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[DirectoryUser]: ...

    async def list_groups(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryGroup]: ...

    async def get_user(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, user_provider_id: str
    ) -> DirectoryUser | None: ...


@runtime_checkable
class StorageProvider(Protocol):
    async def list_sites(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> list[SharePointSite]: ...

    async def list_items(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DriveItem]: ...

    async def download(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        item_provider_id: str,
    ) -> bytes: ...

    async def upload(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DriveItem: ...

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
    ) -> Page[DriveItem]: ...


@runtime_checkable
class MeetingProvider(Protocol):
    """Teams channels, chats, and messages."""

    async def list_channels(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, team_provider_id: str
    ) -> list[TeamsChannel]: ...

    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        conversation_provider_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[TeamsMessage]: ...

    async def post_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message: TeamsMessage
    ) -> str: ...


@runtime_checkable
class PresenceProvider(Protocol):
    async def get_presence(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, user_provider_ids: list[str]
    ) -> list[Presence]: ...


@runtime_checkable
class NotificationProvider(Protocol):
    async def send(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, notification: Notification
    ) -> str: ...


@runtime_checkable
class TaskProvider(Protocol):
    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        source: str = "todo",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceTask]: ...

    async def create_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task: WorkspaceTask
    ) -> str: ...

    async def complete_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task_provider_id: str
    ) -> None: ...


@runtime_checkable
class WorkspaceProvider(Protocol):
    """The aggregate provider — exposes every capability plus webhook management.

    An adapter implements this once and business logic reaches every capability
    through it. ``provider`` names the vendor; ``healthcheck`` reports reachability.
    """

    @property
    def provider(self) -> Provider: ...

    @property
    def mail(self) -> MailProvider: ...

    @property
    def calendar(self) -> CalendarProvider: ...

    @property
    def contacts(self) -> ContactsProvider: ...

    @property
    def directory(self) -> DirectoryProvider: ...

    @property
    def storage(self) -> StorageProvider: ...

    @property
    def meetings(self) -> MeetingProvider: ...

    @property
    def presence(self) -> PresenceProvider: ...

    @property
    def notifications(self) -> NotificationProvider: ...

    @property
    def tasks(self) -> TaskProvider: ...

    async def healthcheck(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> bool: ...

    async def create_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription: ...

    async def renew_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, subscription: WebhookSubscription
    ) -> WebhookSubscription: ...

    async def delete_subscription(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, provider_subscription_id: str
    ) -> None: ...
