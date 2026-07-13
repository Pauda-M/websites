from __future__ import annotations

import uuid

from pb_api.cognitive.domain.common import MemoryType
from pb_api.cognitive.services import CognitiveCore


async def test_consolidation_merges_duplicates(core: CognitiveCore, tenant: uuid.UUID) -> None:
    # Two identical summaries -> identical embeddings -> duplicate.
    await core.episodic.record(tenant_id=tenant, actor="a", summary="Acme signed the contract")
    await core.episodic.record(tenant_id=tenant, actor="a", summary="Acme signed the contract")
    report = await core.consolidation.consolidate(tenant)
    assert report.duplicates_merged >= 1
    live = await core.memory_repo.list(tenant, include_archived=False)
    # One of the duplicates was archived away.
    assert len(live) == 1


async def test_consolidation_promotes_important_episodic(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    await core.episodic.record(
        tenant_id=tenant, actor="a", summary="Critical outage resolved", importance=0.9
    )
    report = await core.consolidation.consolidate(tenant)
    assert report.promoted >= 1
    long_term = await core.memory_repo.list(tenant, memory_type=MemoryType.LONG_TERM)
    assert len(long_term) == 1
    assert "promoted_from" in long_term[0].metadata


async def test_consolidation_archives_stale(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.episodic.record(tenant_id=tenant, actor="a", summary="trivial note", importance=0.1)
    memory = (await core.memory_repo.list(tenant))[0]
    memory.strength = 0.01  # below the archive threshold
    await core.memory_repo.update(memory)
    report = await core.consolidation.consolidate(tenant)
    assert report.archived >= 1
    assert await core.memory_repo.list(tenant, include_archived=False) == []


async def test_consolidation_is_idempotent(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.episodic.record(tenant_id=tenant, actor="a", summary="stable memory", importance=0.9)
    first = await core.consolidation.consolidate(tenant)
    second = await core.consolidation.consolidate(tenant)
    # Second pass promotes nothing new (already promoted) and merges nothing.
    assert first.promoted >= 1
    assert second.duplicates_merged == 0
