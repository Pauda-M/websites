"""Calendar service — meetings, availability, conflict detection, and summaries.

Reads and writes calendar events through the ``CalendarProvider`` port only.
Creating an invite or responding to one is an outbound action and passes the
approval engine. Availability, meeting suggestions, and conflict detection are
computed from provider data; meeting summaries and action items are recorded onto
the event and indexed for search. Timezone-aware throughout.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime, timedelta

from pb_api.integrations.workspace.application.approval_engine import ApprovalEngine
from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.approval import CommunicationType, OutboundAction
from pb_api.integrations.workspace.domain.calendar import (
    AvailabilitySlot,
    CalendarEvent,
    MeetingConflict,
    TimeSlot,
)
from pb_api.integrations.workspace.domain.common import ensure_aware
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.ports.providers import CalendarProvider


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return ensure_aware(a_start) < ensure_aware(b_end) and ensure_aware(b_start) < ensure_aware(
        a_end
    )


class CalendarService:
    def __init__(
        self,
        *,
        provider: CalendarProvider,
        approvals: ApprovalEngine,
        projector: WorkspaceEventProjector,
        search: SearchService,
        settings: WorkspaceSettings,
    ) -> None:
        self._provider = provider
        self._approvals = approvals
        self._projector = projector
        self._search = search
        self._settings = settings

    async def list_events(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> builtins.list[CalendarEvent]:
        page = await self._provider.list_events(
            tenant_id, connection_id, page_size=self._settings.sync_page_size
        )
        return list(page.items)

    async def availability(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        attendee_provider_ids: builtins.list[str],
        window_start: datetime,
        window_end: datetime,
        slot_minutes: int = 30,
    ) -> builtins.list[AvailabilitySlot]:
        return await self._provider.availability(
            tenant_id,
            connection_id,
            attendee_provider_ids=attendee_provider_ids,
            window_start=window_start,
            window_end=window_end,
            slot_minutes=slot_minutes,
        )

    async def suggest_slots(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        attendee_provider_ids: builtins.list[str],
        window_start: datetime,
        window_end: datetime,
        slot_minutes: int = 30,
        limit: int = 3,
    ) -> builtins.list[TimeSlot]:
        """Suggest the first ``limit`` slots where every attendee is free."""
        slots = await self.availability(
            tenant_id,
            connection_id,
            attendee_provider_ids=attendee_provider_ids,
            window_start=window_start,
            window_end=window_end,
            slot_minutes=slot_minutes,
        )
        return [slot.slot for slot in slots if slot.all_free][:limit]

    async def detect_conflicts(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, proposed: TimeSlot
    ) -> MeetingConflict:
        """Detect existing events overlapping a proposed slot."""
        events = await self.list_events(tenant_id, connection_id)
        conflicting = [
            event.provider_id or str(event.id)
            for event in events
            if not event.is_cancelled
            and _overlaps(proposed.start, proposed.end, event.start, event.end)
        ]
        return MeetingConflict(slot=proposed, conflicting_event_ids=conflicting)

    async def create_event(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        event: CalendarEvent,
        agent_id: uuid.UUID | None = None,
        actor_authority: int = 0,
    ) -> dict[str, object]:
        """Create a meeting invite, gated by the approval engine."""
        decision, request = await self._approvals.submit(
            OutboundAction(
                tenant_id=tenant_id,
                communication_type=CommunicationType.MEETING_INVITE,
                actor_authority=actor_authority,
                agent_id=agent_id,
                summary=f"Meeting invite: {event.subject}",
            )
        )
        if not decision.is_automatic:
            return {"decision": decision, "created": False, "approval_request": request}
        provider_id = await self._provider.create_event(tenant_id, connection_id, event)
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MEETING_CREATED,
            summary=f"Created meeting: {event.subject}",
            payload={"provider_id": provider_id},
        )
        await self._search.index_text(
            tenant_id,
            kind="meeting",
            source_provider_id=provider_id,
            title=event.subject,
            body=event.body,
            connection_id=connection_id,
        )
        return {"decision": decision, "created": True, "provider_id": provider_id}

    async def respond(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        event_provider_id: str,
        response: str,
        agent_id: uuid.UUID | None = None,
        actor_authority: int = 0,
    ) -> dict[str, object]:
        decision, request = await self._approvals.submit(
            OutboundAction(
                tenant_id=tenant_id,
                communication_type=CommunicationType.MEETING_RESPONSE,
                actor_authority=actor_authority,
                agent_id=agent_id,
                summary=f"Meeting response: {response}",
            )
        )
        if not decision.is_automatic:
            return {"decision": decision, "responded": False, "approval_request": request}
        await self._provider.respond(tenant_id, connection_id, event_provider_id, response)
        event_type = (
            WorkspaceEventType.MEETING_ACCEPTED
            if response == "accepted"
            else WorkspaceEventType.MEETING_DECLINED
        )
        await self._projector.project(
            tenant_id,
            event_type=event_type,
            summary=f"Responded {response} to meeting {event_provider_id}",
            memorize=False,
        )
        return {"decision": decision, "responded": True}

    async def summarize_meeting(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        event: CalendarEvent,
        summary: str,
        action_items: builtins.list[str],
    ) -> CalendarEvent:
        """Record a meeting summary + extracted action items and index them."""
        event.summary = summary
        event.action_items = action_items
        if event.provider_id is not None:
            await self._provider.update_event(tenant_id, connection_id, event)
        await self._search.index_text(
            tenant_id,
            kind="meeting",
            source_provider_id=event.provider_id or str(event.id),
            title=f"Summary: {event.subject}",
            body=summary + "\n" + "\n".join(action_items),
            connection_id=connection_id,
        )
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.MEETING_UPDATED,
            summary=f"Summarized meeting: {event.subject}",
            payload={"action_items": len(action_items)},
        )
        return event

    @staticmethod
    def default_window(now: datetime, *, days: int = 5) -> tuple[datetime, datetime]:
        return now, now + timedelta(days=days)
