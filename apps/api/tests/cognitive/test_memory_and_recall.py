from __future__ import annotations

import uuid

from pb_api.cognitive.domain.common import MemoryType
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.ranking import RankingContext
from pb_api.cognitive.services import CognitiveCore


async def test_episodic_record_writes_memory_and_event(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    customer = uuid.uuid4()
    event = await core.episodic.record(
        tenant_id=tenant,
        actor="sales_manager",
        summary="Called Acme about renewal",
        customer=customer,
        importance=0.8,
    )
    assert event.organization == tenant
    assert event.embedding is not None  # backfilled by the embedder

    memories = await core.memory_repo.list(tenant, memory_type=MemoryType.EPISODIC)
    assert len(memories) == 1
    assert memories[0].source_event_id == event.id
    assert customer in memories[0].related_entity_ids

    events = await core.events.history(tenant, event_type=EventType.MEMORY_ITEM_CREATED)
    assert len(events) == 1


async def test_recall_ranks_relevant_memories_first(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.episodic.record(
        tenant_id=tenant, actor="a", summary="Acme renewal proposal sent", importance=0.6
    )
    await core.episodic.record(
        tenant_id=tenant, actor="a", summary="Weather is sunny today", importance=0.6
    )
    memories = await core.memory_repo.list(tenant)
    from pb_api.cognitive.domain.common import hash_embedding

    ranking = core.ranker.rank(
        memories,
        RankingContext(
            tenant_id=tenant, query="Acme renewal", query_embedding=hash_embedding("Acme renewal")
        ),
    )
    assert ranking.ranked[0].memory.content.startswith("Acme renewal")
    assert ranking.ranked[0].score >= ranking.ranked[-1].score
    assert "sim=" in ranking.ranked[0].reason


async def test_episodic_is_tenant_isolated(
    core: CognitiveCore, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    await core.episodic.record(tenant_id=tenant, actor="a", summary="secret")
    assert await core.episodic.recent(other_tenant) == []


async def test_touch_reinforces_strength(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.episodic.record(tenant_id=tenant, actor="a", summary="reinforce me")
    memory = (await core.memory_repo.list(tenant))[0]
    before = memory.strength
    touched = await core.memory_repo.touch(tenant, memory.id)
    assert touched is not None
    assert touched.strength >= before
    assert touched.access_count == 1
