"""Mail domain — a provider-agnostic model of a mailbox message and its drafts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import (
    AttachmentDisposition,
    MessagePriority,
    new_id,
    utcnow,
)


class EmailAddress(BaseModel):
    address: str
    name: str = ""


class Attachment(BaseModel):
    """Mail attachment metadata; ``content`` is loaded on demand, never eagerly."""

    id: str
    name: str
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    disposition: AttachmentDisposition = AttachmentDisposition.ATTACHMENT
    content_id: str | None = None


class WorkspaceMessage(BaseModel):
    """A mailbox message, normalized across providers.

    ``provider_id`` is the vendor's stable id; ``conversation_id`` threads a
    conversation; ``customer_organization_id`` / ``customer_contact_id`` are set by
    customer identification once the sender is matched to the CRM.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    conversation_id: str | None = None
    internet_message_id: str | None = None
    subject: str = ""
    body_preview: str = ""
    body: str = ""
    is_html: bool = False
    sender: EmailAddress
    to: list[EmailAddress] = Field(default_factory=list)
    cc: list[EmailAddress] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=utcnow)
    priority: MessagePriority = MessagePriority.NORMAL
    is_read: bool = False
    is_flagged: bool = False
    categories: list[str] = Field(default_factory=list)
    folder: str = "inbox"
    has_attachments: bool = False
    attachments: list[Attachment] = Field(default_factory=list)
    customer_organization_id: uuid.UUID | None = None
    customer_contact_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DraftReply(BaseModel):
    """A reply/forward the Program Manager prepared, before it is sent.

    Kind is one of ``reply`` / ``reply_all`` / ``forward`` / ``new``. It carries the
    id of the message it answers so the provider can thread it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    kind: str = "reply"
    in_reply_to_provider_id: str | None = None
    conversation_id: str | None = None
    to: list[EmailAddress] = Field(default_factory=list)
    cc: list[EmailAddress] = Field(default_factory=list)
    subject: str = ""
    body: str
    is_html: bool = False
    provider_draft_id: str | None = None  # set once persisted with the provider
    created_at: datetime = Field(default_factory=utcnow)
