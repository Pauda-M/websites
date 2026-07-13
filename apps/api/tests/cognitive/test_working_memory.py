from __future__ import annotations

import uuid

from pb_api.cognitive.services import CognitiveCore


async def test_remember_is_token_aware_and_versioned(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    scope = "task:1"
    first = await core.working_memory.remember(tenant, scope, "hello world", relevance=0.9)
    second = await core.working_memory.remember(tenant, scope, "second entry", relevance=0.5)
    assert first.token_estimate > 0
    assert first.version == 1
    assert second.version == 2
    assert first.expires_at is not None


async def test_build_set_orders_by_relevance_and_respects_budget(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    scope = "task:budget"
    # Each ~long entry; the tiny 400-token test budget forces truncation.
    await core.working_memory.remember(tenant, scope, "A" * 1000, relevance=0.9)
    await core.working_memory.remember(tenant, scope, "B" * 1000, relevance=0.8)
    await core.working_memory.remember(tenant, scope, "C" * 1000, relevance=0.1)
    built = await core.working_memory.build_set(tenant, scope)
    assert built.total_tokens <= built.token_budget
    assert built.truncated is True
    # Highest-relevance entry is retained.
    assert built.entries[0].content.startswith("A")


async def test_working_memory_is_tenant_isolated(
    core: CognitiveCore, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    await core.working_memory.remember(tenant, "s", "mine")
    built_other = await core.working_memory.build_set(other_tenant, "s")
    assert built_other.entries == []


async def test_merge_scopes(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.working_memory.remember(tenant, "a", "from a")
    await core.working_memory.remember(tenant, "b", "from b")
    merged = await core.working_memory.merge_scopes(tenant, ["a", "b"], "target")
    assert merged == 2
    built = await core.working_memory.build_set(tenant, "target")
    assert {e.source for e in built.entries} == {"merge"}


async def test_clear_scope(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.working_memory.remember(tenant, "s", "x")
    removed = await core.working_memory.clear(tenant, "s")
    assert removed == 1
    built = await core.working_memory.build_set(tenant, "s")
    assert built.entries == []
