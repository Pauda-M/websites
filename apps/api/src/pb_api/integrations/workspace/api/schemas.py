"""Request bodies for the workspace integration HTTP API (Pydantic v2).

There is no tenant authentication in the platform yet, so every write body carries
an explicit ``tenant_id``. Domain enums are reused directly so the wire contract and
the domain never drift. Server-assigned identifiers, versions, timestamps, and
computed state are never accepted from clients — routes build domain models from
these bodies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from pb_api.integrations.workspace.domain.approval import CommunicationType
from pb_api.integrations.workspace.domain.common import ApprovalDecisionType

# --- Connections -------------------------------------------------------


class ConnectRequest(BaseModel):
    tenant_id: uuid.UUID
    display_name: str
    mailbox: str
    provider_tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str | None = None
    scopes: list[str] | None = None


# --- Synchronization ---------------------------------------------------


class SyncRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID


# --- Mail --------------------------------------------------------------


class ReplyRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    message_provider_id: str
    body: str
    kind: str = "reply"
    agent_id: uuid.UUID | None = None
    actor_authority: int = 0


class CategorizeRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    categories: list[str]


class MoveRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    destination_folder: str


class FlagRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    flagged: bool


# --- Calendar ----------------------------------------------------------


class AvailabilityRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    attendee_provider_ids: list[str]
    window_start: datetime
    window_end: datetime
    slot_minutes: int = 30


class CreateEventRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    subject: str
    body: str = ""
    start: datetime
    end: datetime
    attendee_addresses: list[str] = Field(default_factory=list)
    location: str | None = None
    agent_id: uuid.UUID | None = None
    actor_authority: int = 0


class RespondEventRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    response: str  # one of "accepted" | "declined" | "tentative"


# --- Documents ---------------------------------------------------------


class IngestRequest(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    drive_id: str


# --- Approvals ---------------------------------------------------------


class ApprovalDecisionRequest(BaseModel):
    tenant_id: uuid.UUID
    approve: bool
    decided_by: str


class ApprovalPolicyRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str
    decision: ApprovalDecisionType
    communication_type: CommunicationType | None = None
    customer_organization_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    min_authority: int = 0
    priority: int = 100
