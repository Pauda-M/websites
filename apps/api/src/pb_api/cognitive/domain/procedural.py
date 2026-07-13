"""Procedural memory: reusable, executable workflow definitions.

Examples: Lead Qualification, Proposal Creation, Project Kickoff,
Customer Follow-up, Support Ticket. A ``Procedure`` is a reusable template; the
Workflow Engine (`docs/genesis/010_Workflow_Engine.md`) instantiates and runs
them. The Cognitive Core owns the definitions (Procedural memory).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class ProcedureStep(BaseModel):
    """One ordered step in a procedure."""

    key: str
    title: str
    description: str = ""
    # Named capability/tool this step invokes, if any (see Tool Registry).
    capability: str | None = None
    # Keys of steps that must complete before this one.
    depends_on: list[str] = Field(default_factory=list)
    # Whether the step requires human approval before it runs.
    requires_approval: bool = False


class Procedure(BaseModel):
    """A reusable workflow definition held in procedural memory."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    slug: str  # stable identifier, e.g. "lead-qualification"
    name: str
    description: str = ""
    version: int = 1
    steps: list[ProcedureStep] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
