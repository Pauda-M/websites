"""Calendar routes: list events, compute availability, create invites, respond."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.api.schemas import (
    AvailabilityRequest,
    CreateEventRequest,
    RespondEventRequest,
)
from pb_api.integrations.workspace.domain.calendar import (
    Attendee,
    AvailabilitySlot,
    CalendarEvent,
)
from pb_api.integrations.workspace.domain.mail import EmailAddress

router = APIRouter(prefix="/calendar", tags=["workspace"])


@router.get("")
async def list_events(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
) -> list[CalendarEvent]:
    return await ctx.calendar.list_events(tenant_id, connection_id)


@router.post("/availability")
async def availability(body: AvailabilityRequest, ctx: WsDep) -> list[AvailabilitySlot]:
    return await ctx.calendar.availability(
        body.tenant_id,
        body.connection_id,
        attendee_provider_ids=body.attendee_provider_ids,
        window_start=body.window_start,
        window_end=body.window_end,
        slot_minutes=body.slot_minutes,
    )


@router.post("/events")
async def create_event(body: CreateEventRequest, ctx: WsDep) -> dict[str, object]:
    event = CalendarEvent(
        tenant_id=body.tenant_id,
        subject=body.subject,
        body=body.body,
        start=body.start,
        end=body.end,
        location=body.location,
        attendees=[
            Attendee(email=EmailAddress(address=address)) for address in body.attendee_addresses
        ],
    )
    return await ctx.calendar.create_event(
        body.tenant_id,
        body.connection_id,
        event=event,
        agent_id=body.agent_id,
        actor_authority=body.actor_authority,
    )


@router.post("/events/{event_provider_id}/respond")
async def respond_event(
    event_provider_id: str, body: RespondEventRequest, ctx: WsDep
) -> dict[str, object]:
    return await ctx.calendar.respond(
        body.tenant_id,
        body.connection_id,
        event_provider_id=event_provider_id,
        response=body.response,
    )
