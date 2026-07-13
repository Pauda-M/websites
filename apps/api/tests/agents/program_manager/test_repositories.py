"""Repository-level tests: JSON round-trips and tenant scoping at the data edge."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.agents.program_manager.domain.proposal import (
    PROPOSAL_SECTION_ORDER,
    Proposal,
    ProposalSection,
)
from pb_api.agents.program_manager.domain.run import PMRun, PMTriggerType
from pb_api.agents.program_manager.infrastructure.proposal_repository import ProposalRepository
from pb_api.agents.program_manager.infrastructure.run_repositories import PMRunRepository


async def test_proposal_sections_round_trip_through_json(
    session: AsyncSession, tenant: uuid.UUID
) -> None:
    repo = ProposalRepository(session)
    proposal = Proposal(
        tenant_id=tenant,
        organization_id=uuid.uuid4(),
        title="P",
        sections=[
            ProposalSection(kind=kind, title=kind.value, content=f"body {i}", order=i)
            for i, kind in enumerate(PROPOSAL_SECTION_ORDER)
        ],
    )
    await repo.add(proposal)
    loaded = await repo.get(tenant, proposal.id)
    assert loaded is not None
    assert len(loaded.sections) == 11
    assert loaded.sections[0].kind is PROPOSAL_SECTION_ORDER[0]
    assert loaded.sections[3].content == "body 3"


async def test_run_states_visited_and_enum_round_trip(
    session: AsyncSession, tenant: uuid.UUID
) -> None:
    repo = PMRunRepository(session)
    run = PMRun(tenant_id=tenant, trigger=PMTriggerType.SCHEDULED_ACTION)
    run.states_visited = ["observe", "understand"]
    stored = await repo.add(run)
    stored.states_visited.append("plan")
    await repo.update(stored)
    loaded = await repo.get(tenant, run.id)
    assert loaded is not None
    assert loaded.trigger is PMTriggerType.SCHEDULED_ACTION
    assert loaded.states_visited == ["observe", "understand", "plan"]


async def test_run_repository_is_tenant_scoped(
    session: AsyncSession, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    repo = PMRunRepository(session)
    run = await repo.add(PMRun(tenant_id=tenant, trigger=PMTriggerType.MANUAL))
    assert await repo.get(other_tenant, run.id) is None
    assert await repo.list(other_tenant) == []
