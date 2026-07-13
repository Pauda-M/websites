"""Cognitive domain events.

Everything of consequence becomes an immutable event (Phase 7 spec). Event types
follow the canonical Genesis pattern ``pb.<context>.<aggregate>.<past-verb>``
(`docs/genesis/005_Event_Model.md`, `000_Glossary.md` §9). The Event Processor
persists these to the append-only event store.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class EventType:
    """Canonical cognitive event type constants (closed registry §9.1)."""

    # memory context
    MEMORY_ITEM_CREATED = "pb.memory.item.created"
    MEMORY_ITEM_RECALLED = "pb.memory.item.recalled"
    MEMORY_ITEM_CONSOLIDATED = "pb.memory.item.consolidated"
    MEMORY_ITEM_PROMOTED = "pb.memory.item.promoted"
    MEMORY_ITEM_ARCHIVED = "pb.memory.item.archived"
    MEMORY_ITEM_DEDUPLICATED = "pb.memory.item.deduplicated"
    MEMORY_ITEM_SUMMARIZED = "pb.memory.item.summarized"
    # knowledge context
    KNOWLEDGE_ITEM_CREATED = "pb.knowledge.item.created"
    KNOWLEDGE_ITEM_SUPERSEDED = "pb.knowledge.item.superseded"
    KNOWLEDGE_RELATIONSHIP_ASSERTED = "pb.knowledge.relationship.asserted"
    # agent context (cognition lives under agent per §9.1)
    AGENT_REGISTERED = "pb.agent.registered"
    AGENT_STATUS_CHANGED = "pb.agent.status_changed"
    AGENT_GOAL_CREATED = "pb.agent.goal.created"
    AGENT_GOAL_UPDATED = "pb.agent.goal.updated"
    AGENT_PLAN_CREATED = "pb.agent.plan.created"
    AGENT_REFLECTION_RECORDED = "pb.agent.reflection.recorded"
    AGENT_ACTION_EVALUATED = "pb.agent.action.evaluated"
    # workflow / procedural
    WORKFLOW_PROCEDURE_REGISTERED = "pb.workflow.procedure.registered"


class CognitiveEvent(BaseModel):
    """An immutable domain event with the canonical Genesis envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    type: str
    tenant_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=utcnow)
    actor: str = "system"
    aggregate_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    causation_id: uuid.UUID | None = None
    schema_version: int = 1
    payload: dict[str, object] = Field(default_factory=dict)
