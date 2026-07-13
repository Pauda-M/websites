"""Calendar capability over Microsoft Graph (events, calendarView, getSchedule)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from pb_api.integrations.workspace.domain.calendar import (
    Attendee,
    AttendeeResponse,
    AvailabilitySlot,
    CalendarEvent,
    TimeSlot,
)
from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.mail import EmailAddress
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.graph.client import (
    GraphClient,
    parse_graph_datetime,
    to_graph_utc_iso,
)
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver

# How wide a window to open when a delta sweep starts fresh (calendarView requires
# an explicit range). Resumed sweeps carry their own range in the delta token.
_DELTA_WINDOW_PAST = timedelta(days=30)
_DELTA_WINDOW_FUTURE = timedelta(days=180)

_RESPONSE_ACTIONS = {
    "accept": "accept",
    "accepted": "accept",
    "decline": "decline",
    "declined": "decline",
    "tentative": "tentativelyAccept",
    "tentatively_accept": "tentativelyAccept",
    "tentativelyaccept": "tentativelyAccept",
    "tentativelyaccepted": "tentativelyAccept",
}
_STATUS_TO_RESPONSE = {
    "accepted": AttendeeResponse.ACCEPTED,
    "declined": AttendeeResponse.DECLINED,
    "tentativelyaccepted": AttendeeResponse.TENTATIVE,
}
# Graph availabilityView digits: '0' free, '1' tentative, '2' busy, '3' oof, '4' elsewhere.
_FREE_CODE = "0"


class GraphCalendarProvider:
    """Implements :class:`CalendarProvider` against a Graph calendar."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[CalendarEvent]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.paginate(
            f"/users/{mailbox}/events",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size, "$orderby": "start/dateTime"},
            cursor=cursor,
            map_item=lambda item: _to_event(item, tenant_id),
        )

    async def delta_events(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[CalendarEvent]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        params: dict[str, Any] | None = None
        if cursor is None and delta_token is None:
            now = utcnow()
            params = {
                "startDateTime": to_graph_utc_iso(now - _DELTA_WINDOW_PAST),
                "endDateTime": to_graph_utc_iso(now + _DELTA_WINDOW_FUTURE),
            }
        return await self._client.delta(
            f"/users/{mailbox}/calendarView",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params=params,
            delta_token=delta_token,
            cursor=cursor,
            map_item=lambda item: _to_event(item, tenant_id),
        )

    async def create_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> str:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        response = await self._client.post(
            f"/users/{mailbox}/events",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=_event_body(event),
        )
        return str(response.json().get("id", ""))

    async def update_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event: CalendarEvent
    ) -> None:
        if not event.provider_id:
            raise GraphError(
                "cannot update an event without a provider id",
                status_code=400,
                code="MissingProviderId",
            )
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        await self._client.patch(
            f"/users/{mailbox}/events/{event.provider_id}",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=_event_body(event),
        )

    async def cancel_event(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, event_provider_id: str
    ) -> None:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        await self._client.post(
            f"/users/{mailbox}/events/{event_provider_id}/cancel",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"comment": ""},
        )

    async def respond(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        event_provider_id: str,
        response: str,
    ) -> None:
        action = _RESPONSE_ACTIONS.get(response.strip().lower())
        if action is None:
            raise GraphError(
                f"unsupported meeting response '{response}'",
                status_code=400,
                code="UnsupportedResponse",
            )
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        await self._client.post(
            f"/users/{mailbox}/events/{event_provider_id}/{action}",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"sendResponse": True, "comment": ""},
        )

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
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        response = await self._client.post(
            f"/users/{mailbox}/calendar/getSchedule",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={
                "schedules": attendee_provider_ids,
                "startTime": {"dateTime": to_graph_utc_iso(window_start), "timeZone": "UTC"},
                "endTime": {"dateTime": to_graph_utc_iso(window_end), "timeZone": "UTC"},
                "availabilityViewInterval": slot_minutes,
            },
        )
        schedules = response.json().get("value", [])
        return _availability_slots(
            schedules if isinstance(schedules, list) else [],
            window_start=window_start,
            window_end=window_end,
            slot_minutes=slot_minutes,
        )


def _availability_slots(
    schedules: list[Any],
    *,
    window_start: datetime,
    window_end: datetime,
    slot_minutes: int,
) -> list[AvailabilitySlot]:
    interval = timedelta(minutes=slot_minutes)
    total_seconds = max((window_end - window_start).total_seconds(), 0.0)
    slot_count = int(total_seconds // (slot_minutes * 60))
    views = [
        (str(item.get("scheduleId", "")), str(item.get("availabilityView", "")))
        for item in schedules
        if isinstance(item, dict)
    ]
    slots: list[AvailabilitySlot] = []
    for index in range(slot_count):
        slot_start = window_start + interval * index
        free = [
            schedule_id
            for schedule_id, view in views
            if (view[index] if index < len(view) else _FREE_CODE) == _FREE_CODE
        ]
        slots.append(
            AvailabilitySlot(
                slot=TimeSlot(start=slot_start, end=slot_start + interval),
                free_attendees=free,
                all_free=len(free) == len(views),
            )
        )
    return slots


def _event_body(event: CalendarEvent) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subject": event.subject,
        "body": {"contentType": "HTML", "content": event.body},
        "start": {"dateTime": to_graph_utc_iso(event.start), "timeZone": "UTC"},
        "end": {"dateTime": to_graph_utc_iso(event.end), "timeZone": "UTC"},
        "isAllDay": event.is_all_day,
        "categories": event.categories,
    }
    if event.location:
        body["location"] = {"displayName": event.location}
    if event.attendees:
        body["attendees"] = [
            {
                "emailAddress": {"address": attendee.email.address, "name": attendee.email.name},
                "type": "required" if attendee.required else "optional",
            }
            for attendee in event.attendees
        ]
    return body


def _to_event(data: Any, tenant_id: uuid.UUID) -> CalendarEvent:
    if not isinstance(data, dict):
        data = {}
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    start = data.get("start") if isinstance(data.get("start"), dict) else {}
    end = data.get("end") if isinstance(data.get("end"), dict) else {}
    location = data.get("location") if isinstance(data.get("location"), dict) else {}
    online = data.get("onlineMeeting") if isinstance(data.get("onlineMeeting"), dict) else {}
    return CalendarEvent(
        tenant_id=tenant_id,
        provider_id=_optional_str(data.get("id")),
        subject=str(data.get("subject", "")),
        body=str(body.get("content", "")),
        start=parse_graph_datetime(start.get("dateTime")) or utcnow(),
        end=parse_graph_datetime(end.get("dateTime")) or utcnow(),
        timezone=str(start.get("timeZone", "UTC")),
        location=_optional_str(location.get("displayName")),
        online_meeting_url=_optional_str(online.get("joinUrl") or data.get("onlineMeetingUrl")),
        organizer=_to_email_address(data.get("organizer")) if data.get("organizer") else None,
        attendees=[_to_attendee(item) for item in _as_list(data.get("attendees"))],
        is_all_day=bool(data.get("isAllDay", False)),
        is_cancelled=bool(data.get("isCancelled", False)),
        categories=[str(category) for category in _as_list(data.get("categories"))],
    )


def _to_attendee(data: Any) -> Attendee:
    if not isinstance(data, dict):
        data = {}
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    response = str(status.get("response", "none")).lower()
    return Attendee(
        email=_to_email_address(data),
        required=str(data.get("type", "required")).lower() != "optional",
        response=_STATUS_TO_RESPONSE.get(response, AttendeeResponse.NONE),
    )


def _to_email_address(data: Any) -> EmailAddress:
    email = data.get("emailAddress", {}) if isinstance(data, dict) else {}
    if not isinstance(email, dict):
        email = {}
    return EmailAddress(address=str(email.get("address", "")), name=str(email.get("name", "")))


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
