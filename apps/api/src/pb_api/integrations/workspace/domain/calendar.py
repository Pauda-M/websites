"""Calendar domain — events, attendees, availability, and meeting artifacts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow
from pb_api.integrations.workspace.domain.mail import EmailAddress


class AttendeeResponse(enum.StrEnum):
    NONE = "none"
    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"


class Attendee(BaseModel):
    email: EmailAddress
    required: bool = True
    response: AttendeeResponse = AttendeeResponse.NONE


class CalendarEvent(BaseModel):
    """A calendar event, normalized across providers. Times are timezone-aware."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str | None = None
    subject: str = ""
    body: str = ""
    start: datetime
    end: datetime
    timezone: str = "UTC"
    location: str | None = None
    online_meeting_url: str | None = None
    organizer: EmailAddress | None = None
    attendees: list[Attendee] = Field(default_factory=list)
    is_all_day: bool = False
    is_cancelled: bool = False
    categories: list[str] = Field(default_factory=list)
    summary: str = ""  # meeting summary / minutes
    action_items: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class AvailabilitySlot(BaseModel):
    """A candidate free slot with the set of attendees free for it."""

    slot: TimeSlot
    free_attendees: list[str] = Field(default_factory=list)
    all_free: bool = True


class MeetingConflict(BaseModel):
    """A detected overlap between a proposed slot and existing events."""

    slot: TimeSlot
    conflicting_event_ids: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=utcnow)
