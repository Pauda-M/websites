"""Context Builder and Prompt Builder output models."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from pb_api.cognitive.domain.common import new_id


class ContextSection(BaseModel):
    """One labelled section of a built context (e.g. 'goals', 'memories')."""

    name: str
    content: str
    token_estimate: int = 0
    item_count: int = 0


class BuiltContext(BaseModel):
    """The optimised, token-bounded context assembled for a reasoning step."""

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    scope_key: str
    sections: list[ContextSection] = Field(default_factory=list)
    total_tokens: int = 0
    token_budget: int
    truncated: bool = False


class AssembledPrompt(BaseModel):
    """A dynamically assembled prompt — never a static template."""

    tenant_id: uuid.UUID
    system: str
    context: BuiltContext
    token_estimate: int = 0
    sections_included: list[str] = Field(default_factory=list)
