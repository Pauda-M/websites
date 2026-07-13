"""Proposal routes: draft an eleven-section proposal, list, fetch, mark ready."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.agents.program_manager.api.deps import PMDep
from pb_api.agents.program_manager.api.schemas import ProposalDraftRequest, ProposalReadyRequest
from pb_api.agents.program_manager.domain.proposal import Proposal, ProposalStatus

router = APIRouter(prefix="/proposals", tags=["program-manager-proposals"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def draft_proposal(body: ProposalDraftRequest, pm: PMDep) -> Proposal:
    return await pm.proposals.draft_proposal(
        tenant_id=body.tenant_id,
        organization_id=body.organization_id,
        title=body.title,
        opportunity_id=body.opportunity_id,
        total_value=body.total_value,
        currency=body.currency,
        sections=body.sections,
    )


@router.get("")
async def list_proposals(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[ProposalStatus | None, Query(alias="status")] = None,
) -> list[Proposal]:
    return await pm.proposals.list(tenant_id, organization_id=organization_id, status=status_filter)


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: uuid.UUID, pm: PMDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> Proposal:
    proposal = await pm.proposals.get(tenant_id, proposal_id)
    if proposal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="proposal not found")
    return proposal


@router.post("/{proposal_id}/ready")
async def mark_ready(proposal_id: uuid.UUID, body: ProposalReadyRequest, pm: PMDep) -> Proposal:
    try:
        return await pm.proposals.mark_ready(
            body.tenant_id, proposal_id, approved_by=body.approved_by
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
