"""Synchronization domain — sync state, webhook subscriptions, jobs, and the DLQ.

These model the machinery of keeping Genesis in step with the provider:
per-resource delta cursors, webhook subscriptions (with their expiry), the record
of each sync run, and the dead-letter queue that captures work that exhausted its
retries so it is never silently lost.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import (
    Provider,
    SyncResource,
    SyncStatus,
    new_id,
    utcnow,
)


class SyncState(BaseModel):
    """The persisted delta cursor and status for one (connection, resource)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    resource: SyncResource
    delta_token: str | None = None
    status: SyncStatus = SyncStatus.IDLE
    last_synced_at: datetime | None = None
    last_error: str | None = None
    items_synced: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class WebhookSubscription(BaseModel):
    """A change-notification subscription with the provider (renewed before expiry)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    provider: Provider = Provider.MICROSOFT_GRAPH
    provider_subscription_id: str | None = None
    resource: str  # e.g. "/users/{id}/messages"
    change_types: list[str] = Field(default_factory=lambda: ["created", "updated"])
    notification_url: str
    client_state: str = ""  # secret echoed back to authenticate notifications
    expires_at: datetime | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class SyncJob(BaseModel):
    """A record of a single synchronization run, for observability and auditing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    resource: SyncResource
    status: SyncStatus = SyncStatus.RUNNING
    items_processed: int = 0
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None


class DeadLetter(BaseModel):
    """A unit of work that exhausted its retries — captured, never dropped."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    kind: str  # e.g. "sync:mail", "webhook:notification", "outbound:mail"
    payload: dict[str, object] = Field(default_factory=dict)
    error: str
    attempts: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class WebhookNotification(BaseModel):
    """A normalized change notification delivered to the webhook endpoint."""

    subscription_provider_id: str | None = None
    client_state: str = ""
    resource: str
    change_type: str = "updated"
    resource_provider_id: str | None = None
    received_at: datetime = Field(default_factory=utcnow)
