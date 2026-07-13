"""Teams capability over Microsoft Graph (channels, chats, messages).

The port addresses a conversation by a single ``conversation_provider_id``. For a
channel that identifier encodes ``"{teamId}/{channelId}"`` (channel messages live
under a team); for a chat it is the chat id.
"""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.mail import EmailAddress
from pb_api.integrations.workspace.domain.page import Page
from pb_api.integrations.workspace.domain.teams import (
    ConversationKind,
    TeamsChannel,
    TeamsMessage,
)
from pb_api.integrations.workspace.graph.client import GraphClient, parse_graph_datetime
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver


class GraphTeamsProvider:
    """Implements :class:`MeetingProvider` against Teams channels and chats."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_channels(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, team_provider_id: str
    ) -> list[TeamsChannel]:
        page = await self._client.paginate(
            f"/teams/{team_provider_id}/channels",
            tenant_id=tenant_id,
            connection_id=connection_id,
            map_item=lambda item: _to_channel(item, tenant_id, team_provider_id),
        )
        return list(page.items)

    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        conversation_provider_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[TeamsMessage]:
        path = f"{_messages_base(conversation_provider_id)}"
        return await self._client.paginate(
            path,
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size},
            cursor=cursor,
            map_item=lambda item: _to_message(item, tenant_id, conversation_provider_id),
        )

    async def post_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message: TeamsMessage
    ) -> str:
        base = _messages_base(
            message.conversation_provider_id,
            kind=message.conversation_kind,
        )
        if message.reply_to_provider_id:
            base = f"{base}/{message.reply_to_provider_id}/replies"
        response = await self._client.post(
            base,
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"body": {"contentType": "html", "content": message.body}},
        )
        return str(response.json().get("id", ""))


def _messages_base(
    conversation_provider_id: str, *, kind: ConversationKind = ConversationKind.CHANNEL
) -> str:
    if kind is ConversationKind.CHAT and "/" not in conversation_provider_id:
        return f"/chats/{conversation_provider_id}/messages"
    if "/" in conversation_provider_id:
        team_id, channel_id = conversation_provider_id.split("/", 1)
        return f"/teams/{team_id}/channels/{channel_id}/messages"
    if kind is ConversationKind.CHANNEL:
        raise GraphError(
            "channel conversation id must be '{teamId}/{channelId}'",
            status_code=400,
            code="InvalidConversationId",
        )
    return f"/chats/{conversation_provider_id}/messages"


def _to_channel(data: Any, tenant_id: uuid.UUID, team_provider_id: str) -> TeamsChannel:
    if not isinstance(data, dict):
        data = {}
    return TeamsChannel(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        team_provider_id=team_provider_id,
        display_name=str(data.get("displayName", "")),
        description=str(data.get("description", "") or ""),
    )


def _to_message(data: Any, tenant_id: uuid.UUID, conversation_provider_id: str) -> TeamsMessage:
    if not isinstance(data, dict):
        data = {}
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    kind = (
        ConversationKind.CHAT if "/" not in conversation_provider_id else ConversationKind.CHANNEL
    )
    return TeamsMessage(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        conversation_kind=kind,
        conversation_provider_id=conversation_provider_id,
        reply_to_provider_id=_optional_str(data.get("replyToId")),
        sender=_to_sender(data.get("from")),
        body=str(body.get("content", "")),
        mentions=_to_mentions(data.get("mentions")),
        created_at=parse_graph_datetime(data.get("createdDateTime")) or utcnow(),
    )


def _to_sender(data: Any) -> EmailAddress | None:
    if not isinstance(data, dict):
        return None
    user = _as_dict(data.get("user"))
    identifier = user.get("id") or user.get("displayName")
    if not identifier:
        return None
    return EmailAddress(address=str(identifier), name=str(user.get("displayName", "")))


def _to_mentions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    mentions: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        user = _as_dict(_as_dict(item.get("mentioned")).get("user"))
        user_id = user.get("id")
        if isinstance(user_id, str) and user_id:
            mentions.append(user_id)
    return mentions


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
