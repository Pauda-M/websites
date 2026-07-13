from __future__ import annotations

import uuid

import pytest

from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.domain.proposal import (
    PROPOSAL_SECTION_ORDER,
    ProposalSectionKind,
    ProposalStatus,
)


async def test_draft_scaffolds_all_eleven_sections(pm: ProgramManager, tenant: uuid.UUID) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    proposal = await pm.proposals.draft_proposal(
        tenant_id=tenant, organization_id=org.id, title="Acme Proposal"
    )
    assert len(proposal.sections) == 11
    assert [s.kind for s in proposal.sections] == list(PROPOSAL_SECTION_ORDER)
    assert proposal.status is ProposalStatus.DRAFT
    assert proposal.requires_approval is False  # below threshold


async def test_high_value_proposal_requires_approval(pm: ProgramManager, tenant: uuid.UUID) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Big")
    proposal = await pm.proposals.draft_proposal(
        tenant_id=tenant,
        organization_id=org.id,
        title="Big Deal",
        total_value=100_000.0,
    )
    assert proposal.requires_approval is True


async def test_mark_ready_enforces_completeness_then_approval(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    proposal = await pm.proposals.draft_proposal(
        tenant_id=tenant, organization_id=org.id, title="Acme", total_value=100_000.0
    )
    # Incomplete → cannot be ready.
    with pytest.raises(ValueError, match="incomplete"):
        await pm.proposals.mark_ready(tenant, proposal.id)

    for kind in ProposalSectionKind:
        await pm.proposals.update_section(tenant, proposal.id, kind=kind, content="content")

    # Complete but high-value and unapproved → still blocked.
    with pytest.raises(ValueError, match="approval"):
        await pm.proposals.mark_ready(tenant, proposal.id)

    ready = await pm.proposals.mark_ready(tenant, proposal.id, approved_by="alice@pb")
    assert ready.status is ProposalStatus.READY
    assert ready.approved_by == "alice@pb"


async def test_send_requires_ready_then_transitions(pm: ProgramManager, tenant: uuid.UUID) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    proposal = await pm.proposals.draft_proposal(
        tenant_id=tenant, organization_id=org.id, title="Acme"
    )
    with pytest.raises(ValueError, match="READY"):
        await pm.proposals.send(tenant, proposal.id)

    for kind in ProposalSectionKind:
        await pm.proposals.update_section(tenant, proposal.id, kind=kind, content="c")
    await pm.proposals.mark_ready(tenant, proposal.id)
    sent = await pm.proposals.send(tenant, proposal.id)
    assert sent.status is ProposalStatus.SENT
