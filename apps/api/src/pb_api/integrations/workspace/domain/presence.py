"""Presence and notification domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class Availability(enum.StrEnum):
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    DO_NOT_DISTURB = "do_not_disturb"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Presence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    user_provider_id: str
    availability: Availability = Availability.UNKNOWN
    activity: str = ""
    observed_at: datetime = Field(default_factory=utcnow)


class Notification(BaseModel):
    """A notification the workspace surfaces to a human (e.g. a Teams/activity ping)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    channel: str = "teams"  # "teams" | "email" | "activity_feed"
    recipient_provider_id: str
    title: str
    body: str = ""
    link: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)
