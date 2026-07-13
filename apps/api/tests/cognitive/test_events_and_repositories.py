from __future__ import annotations

import uuid

from pb_api.cognitive.domain.common import MemoryType
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.memory import MemoryItem
from pb_api.cognitive.services import CognitiveCore


async def test_event_processor_records_and_correlates(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    correlation = uuid.uuid4()
    first = await core.events.record(
        event_type="pb.agent.task.started", tenant_id=tenant, correlation_id=correlation
    )
    await core.events.record(
        event_type="pb.agent.task.completed",
        tenant_id=tenant,
        correlation_id=correlation,
        causation_id=first.id,
    )
    chain = await core.events.history(tenant, correlation_id=correlation)
    assert len(chain) == 2
    # Ordered by occurred_at ascending (causation chain).
    assert chain[0].type == "pb.agent.task.started"
    assert chain[1].causation_id == first.id


async def test_events_are_tenant_isolated(
    core: CognitiveCore, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    await core.events.record(event_type="pb.agent.task.started", tenant_id=tenant)
    assert await core.events.history(other_tenant) == []


async def test_memory_repository_crud_and_isolation(
    core: CognitiveCore, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    item = await core.memory_repo.add(
        MemoryItem(tenant_id=tenant, memory_type=MemoryType.SEMANTIC, content="fact")
    )
    fetched = await core.memory_repo.get(tenant, item.id)
    assert fetched is not None
    # Cross-tenant read is impossible.
    assert await core.memory_repo.get(other_tenant, item.id) is None
    # Cross-tenant delete is a no-op.
    assert await core.memory_repo.delete(other_tenant, item.id) is False
    assert await core.memory_repo.delete(tenant, item.id) is True
    assert await core.memory_repo.get(tenant, item.id) is None


async def test_domain_event_recorded_for_knowledge(core: CognitiveCore, tenant: uuid.UUID) -> None:
    from pb_api.cognitive.domain.semantic import KnowledgeKind

    await core.semantic.add_knowledge(
        tenant_id=tenant, kind=KnowledgeKind.FACT, name="k", content="v"
    )
    events = await core.events.history(tenant, event_type=EventType.KNOWLEDGE_ITEM_CREATED)
    assert len(events) == 1
