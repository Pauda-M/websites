"""SQLAlchemy ORM models for the workspace integration.

All tables share the platform ``Base`` (`pb_api.db.base`) so a single Alembic
chain and ``metadata.create_all`` cover the whole platform. Every row is
tenant-scoped (``tenant_id``). Portable column types (Uuid, JSON, String, Text,
non-native enums stored as String) keep the suite runnable on SQLite while
production runs PostgreSQL — the same portability contract the Cognitive Core and
Program Manager follow. Tables are prefixed ``ws_``; the domain field ``metadata``
maps to the row column ``meta`` (``metadata`` is reserved on the declarative base).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from pb_api.db.base import Base

JsonList = list[object]
JsonDict = dict[str, object]


class _WsBase(Base):
    """Abstract base: primary key, tenant scope, created timestamp."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Connection & credentials ------------------------------------------


class WorkspaceConnectionRow(_WsBase):
    __tablename__ = "ws_connection"

    provider: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(255))
    mailbox: Mapped[str] = mapped_column(String(320), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceCredentialRow(_WsBase):
    """Stores ONLY encrypted secrets — plaintext is never persisted here."""

    __tablename__ = "ws_credential"

    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    provider_tenant_id: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[JsonList] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Synchronization ---------------------------------------------------


class SyncStateRow(_WsBase):
    __tablename__ = "ws_sync_state"

    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    resource: Mapped[str] = mapped_column(String(30), index=True)
    delta_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncJobRow(_WsBase):
    __tablename__ = "ws_sync_job"

    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    resource: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running")
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeadLetterRow(_WsBase):
    __tablename__ = "ws_dead_letter"

    kind: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class WebhookSubscriptionRow(_WsBase):
    __tablename__ = "ws_webhook_subscription"

    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="microsoft_graph")
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    resource: Mapped[str] = mapped_column(String(500))
    change_types: Mapped[JsonList] = mapped_column(JSON, default=list)
    notification_url: Mapped[str] = mapped_column(String(1000))
    client_state: Mapped[str] = mapped_column(String(255), default="")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# --- Approval ----------------------------------------------------------


class ApprovalPolicyRow(_WsBase):
    __tablename__ = "ws_approval_policy"

    name: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(30))
    communication_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    customer_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    customer_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    min_authority: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")


class ApprovalRequestRow(_WsBase):
    __tablename__ = "ws_approval_request"

    communication_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    customer_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Audit -------------------------------------------------------------


class AuditLogRow(_WsBase):
    __tablename__ = "ws_audit_log"

    action: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(255), default="workspace")
    resource: Mapped[str] = mapped_column(String(500), default="")
    outcome: Mapped[str] = mapped_column(String(20), default="ok")
    detail: Mapped[JsonDict] = mapped_column(JSON, default=dict)


# --- Mail --------------------------------------------------------------


class MailMessageRow(_WsBase):
    __tablename__ = "ws_message"

    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(512), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    internet_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    body_preview: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    is_html: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_address: Mapped[str] = mapped_column(String(320))
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    recipients_to: Mapped[JsonList] = mapped_column(JSON, default=list)
    recipients_cc: Mapped[JsonList] = mapped_column(JSON, default=list)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    categories: Mapped[JsonList] = mapped_column(JSON, default=list)
    folder: Mapped[str] = mapped_column(String(255), default="inbox", index=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attachments: Mapped[JsonList] = mapped_column(JSON, default=list)
    customer_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    customer_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


# --- Unified search index ----------------------------------------------


class IndexEntryRow(_WsBase):
    __tablename__ = "ws_index_entry"

    kind: Mapped[str] = mapped_column(String(50), index=True)
    source_provider_id: Mapped[str] = mapped_column(String(512), index=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    web_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    embedding: Mapped[JsonList] = mapped_column(JSON, default=list)
    ref: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
