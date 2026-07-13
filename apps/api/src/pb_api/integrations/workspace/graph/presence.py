"""Presence capability over Microsoft Graph (``/communications/getPresencesByUserId``)."""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.presence import Availability, Presence
from pb_api.integrations.workspace.graph.client import GraphClient
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver

_AVAILABILITY = {
    "available": Availability.AVAILABLE,
    "availableidle": Availability.AVAILABLE,
    "busy": Availability.BUSY,
    "busyidle": Availability.BUSY,
    "away": Availability.AWAY,
    "berightback": Availability.AWAY,
    "donotdisturb": Availability.DO_NOT_DISTURB,
    "offline": Availability.OFFLINE,
    "presenceunknown": Availability.UNKNOWN,
}


class GraphPresenceProvider:
    """Implements :class:`PresenceProvider` against Teams presence."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def get_presence(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        user_provider_ids: list[str],
    ) -> list[Presence]:
        if not user_provider_ids:
            return []
        response = await self._client.post(
            "/communications/getPresencesByUserId",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"ids": user_provider_ids},
        )
        value = response.json().get("value", [])
        return [_to_presence(item, tenant_id) for item in value if isinstance(item, dict)]


def _to_presence(data: dict[str, Any], tenant_id: uuid.UUID) -> Presence:
    availability = str(data.get("availability", "PresenceUnknown")).lower()
    return Presence(
        tenant_id=tenant_id,
        user_provider_id=str(data.get("id", "")),
        availability=_AVAILABILITY.get(availability, Availability.UNKNOWN),
        activity=str(data.get("activity", "") or ""),
    )
