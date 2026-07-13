"""Teams domain — channels, chats, messages, mentions, and threading."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow
from pb_api.integrations.workspace.domain.mail import EmailAddress


class ConversationKind(enum.StrEnum):
    CHANNEL = "channel"
    CHAT = "chat"


class TeamsChannel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    team_provider_id: str
    display_name: str
    description: str = ""


class TeamsMessage(BaseModel):
    """A message in a channel or chat; ``reply_to_provider_id`` threads replies."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    conversation_kind: ConversationKind = ConversationKind.CHANNEL
    conversation_provider_id: str
    reply_to_provider_id: str | None = None
    sender: EmailAddress | None = None
    body: str = ""
    mentions: list[str] = Field(default_factory=list)  # mentioned user provider ids
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)
