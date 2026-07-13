"""Tenant-scoped async repository for proposals.

A proposal's ordered :class:`ProposalSection` blocks are serialised to JSON
(`model_dump(mode="json")`) on write and reconstructed with
:meth:`ProposalSection.model_validate` on read.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.agents.program_manager.db.models import ProposalRow
from pb_api.agents.program_manager.domain.proposal import (
    Proposal,
    ProposalSection,
    ProposalStatus,
)
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_proposal(row: ProposalRow) -> Proposal:
    return Proposal(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        opportunity_id=row.opportunity_id,
        title=row.title,
        status=ProposalStatus(row.status),
        version=row.version,
        sections=[ProposalSection.model_validate(section) for section in row.sections],
        total_value=row.total_value,
        currency=row.currency,
        valid_until=row.valid_until,
        requires_approval=row.requires_approval,
        approved_by=row.approved_by,
        owner_agent_id=row.owner_agent_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProposalRepository(BaseRepository):
    async def add(self, proposal: Proposal) -> Proposal:
        row = ProposalRow(
            id=proposal.id,
            tenant_id=proposal.tenant_id,
            organization_id=proposal.organization_id,
            opportunity_id=proposal.opportunity_id,
            title=proposal.title,
            status=proposal.status.value,
            version=proposal.version,
            sections=[section.model_dump(mode="json") for section in proposal.sections],
            total_value=proposal.total_value,
            currency=proposal.currency,
            valid_until=proposal.valid_until,
            requires_approval=proposal.requires_approval,
            approved_by=proposal.approved_by,
            owner_agent_id=proposal.owner_agent_id,
            meta=proposal.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_proposal(row)

    async def get(self, tenant_id: uuid.UUID, proposal_id: uuid.UUID) -> Proposal | None:
        row = await self.session.get(ProposalRow, proposal_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_proposal(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        status: ProposalStatus | None = None,
        limit: int = 200,
    ) -> list[Proposal]:
        stmt = select(ProposalRow).where(ProposalRow.tenant_id == tenant_id)
        if organization_id is not None:
            stmt = stmt.where(ProposalRow.organization_id == organization_id)
        if opportunity_id is not None:
            stmt = stmt.where(ProposalRow.opportunity_id == opportunity_id)
        if status is not None:
            stmt = stmt.where(ProposalRow.status == status.value)
        stmt = stmt.order_by(ProposalRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_proposal(row) for row in rows]

    async def update(self, proposal: Proposal) -> Proposal | None:
        row = await self.session.get(ProposalRow, proposal.id)
        if row is None or row.tenant_id != proposal.tenant_id:
            return None
        row.organization_id = proposal.organization_id
        row.opportunity_id = proposal.opportunity_id
        row.title = proposal.title
        row.status = proposal.status.value
        row.version = proposal.version
        row.sections = [section.model_dump(mode="json") for section in proposal.sections]
        row.total_value = proposal.total_value
        row.currency = proposal.currency
        row.valid_until = proposal.valid_until
        row.requires_approval = proposal.requires_approval
        row.approved_by = proposal.approved_by
        row.owner_agent_id = proposal.owner_agent_id
        row.meta = proposal.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_proposal(row)
