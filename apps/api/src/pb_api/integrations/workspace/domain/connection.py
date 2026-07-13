"""Connection domain — a configured link to one workspace provider account.

A :class:`WorkspaceConnection` is the tenant-scoped record of a single provider
mailbox/account the platform is wired to. Credentials for it live separately (and
only ever encrypted) in the credential store; this model carries no secrets.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import Provider, new_id, utcnow


class ConnectionStatus(enum.StrEnum):
    """Lifecycle state of a workspace connection."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class WorkspaceConnection(BaseModel):
    """A configured connection to one workspace provider mailbox/account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider: Provider = Provider.MICROSOFT_GRAPH
    display_name: str = ""
    mailbox: str = ""
    status: str = ConnectionStatus.ACTIVE.value
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
