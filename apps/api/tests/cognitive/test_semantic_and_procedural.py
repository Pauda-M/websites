from __future__ import annotations

import uuid

from pb_api.cognitive.domain.semantic import KnowledgeKind
from pb_api.cognitive.services import CognitiveCore


async def test_semantic_add_and_supersede_preserves_history(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    fact = await core.semantic.add_knowledge(
        tenant_id=tenant,
        kind=KnowledgeKind.FACT,
        name="acme_plan",
        content="Acme is on the Starter plan",
        confidence=0.6,
    )
    assert fact.version == 1

    updated = await core.semantic.update_knowledge(
        tenant_id=tenant, item_id=fact.id, content="Acme upgraded to Pro", confidence=0.9
    )
    assert updated is not None
    assert updated.version == 2

    # Default list hides superseded versions.
    current = await core.semantic.list(tenant)
    assert [item.id for item in current] == [updated.id]
    # History is retained when explicitly requested.
    everything = await core.semantic.list(tenant, include_superseded=True)
    assert fact.id in {item.id for item in everything}


async def test_semantic_relationships_and_neighbors(core: CognitiveCore, tenant: uuid.UUID) -> None:
    a = await core.semantic.add_knowledge(
        tenant_id=tenant, kind=KnowledgeKind.CONCEPT, name="Acme", content="A customer"
    )
    b = await core.semantic.add_knowledge(
        tenant_id=tenant, kind=KnowledgeKind.CONCEPT, name="Jane", content="A contact"
    )
    await core.semantic.relate(
        tenant_id=tenant, source_id=b.id, target_id=a.id, relation="works_at"
    )
    neighbors = await core.semantic.neighbors(tenant, a.id)
    assert len(neighbors) == 1
    assert neighbors[0].relation == "works_at"


async def test_procedural_seed_defaults_are_reusable(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    created = await core.procedural.seed_defaults(tenant)
    slugs = {proc.slug for proc in created}
    assert {
        "lead-qualification",
        "proposal-creation",
        "project-kickoff",
        "customer-follow-up",
        "support-ticket",
    } <= slugs
    # Idempotent: seeding again creates nothing new.
    assert await core.procedural.seed_defaults(tenant) == []

    proposal = await core.procedural.get_by_slug(tenant, "proposal-creation")
    assert proposal is not None
    assert any(step.requires_approval for step in proposal.steps)


async def test_procedural_register_bumps_version(core: CognitiveCore, tenant: uuid.UUID) -> None:
    first = await core.procedural.register(tenant_id=tenant, slug="custom", name="Custom v1")
    second = await core.procedural.register(tenant_id=tenant, slug="custom", name="Custom v2")
    assert first.version == 1
    assert second.version == 2
    latest = await core.procedural.get_by_slug(tenant, "custom")
    assert latest is not None
    assert latest.version == 2
