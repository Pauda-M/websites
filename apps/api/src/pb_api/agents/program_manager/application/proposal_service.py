"""Proposal service — prepares and governs eleven-section proposals.

Scaffolds every proposal with the eleven canonical sections in order, lets the
Program Manager fill them in, and enforces two gates before a proposal may leave
the building: it must be *complete* (all sections filled), and if its value is at
or above the configured threshold it must be *approved* by a human. Sending is
only possible once ready. These are the guardrails that keep proposal automation
from committing the business beyond the Program Manager's authority.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import date

from pb_api.agents.program_manager.config import ProgramManagerSettings
from pb_api.agents.program_manager.domain.events import PMEventType
from pb_api.agents.program_manager.domain.proposal import (
    PROPOSAL_SECTION_ORDER,
    PROPOSAL_SECTION_TITLES,
    Proposal,
    ProposalSection,
    ProposalSectionKind,
    ProposalStatus,
)
from pb_api.agents.program_manager.infrastructure.proposal_repository import ProposalRepository
from pb_api.cognitive.services.event_processor import EventProcessor


def _scaffold_sections(
    content: dict[ProposalSectionKind, str] | None,
) -> builtins.list[ProposalSection]:
    """Build the eleven canonical sections in order, filling any provided content."""
    provided = content or {}
    return [
        ProposalSection(
            kind=kind,
            title=PROPOSAL_SECTION_TITLES[kind],
            content=provided.get(kind, ""),
            order=index,
        )
        for index, kind in enumerate(PROPOSAL_SECTION_ORDER)
    ]


class ProposalService:
    def __init__(
        self,
        proposals: ProposalRepository,
        events: EventProcessor,
        settings: ProgramManagerSettings,
    ) -> None:
        self._proposals = proposals
        self._events = events
        self._settings = settings

    async def draft_proposal(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        title: str,
        opportunity_id: uuid.UUID | None = None,
        total_value: float = 0.0,
        currency: str = "EUR",
        valid_until: date | None = None,
        sections: dict[ProposalSectionKind, str] | None = None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> Proposal:
        requires_approval = total_value >= self._settings.proposal_approval_value_threshold
        proposal = await self._proposals.add(
            Proposal(
                tenant_id=tenant_id,
                organization_id=organization_id,
                opportunity_id=opportunity_id,
                title=title,
                total_value=max(0.0, total_value),
                currency=currency,
                valid_until=valid_until,
                sections=_scaffold_sections(sections),
                requires_approval=requires_approval,
                owner_agent_id=owner_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.PROPOSAL_DRAFTED,
            tenant_id=tenant_id,
            aggregate_id=proposal.id,
            payload={"title": title, "requires_approval": requires_approval},
        )
        return proposal

    async def get(self, tenant_id: uuid.UUID, proposal_id: uuid.UUID) -> Proposal | None:
        return await self._proposals.get(tenant_id, proposal_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        status: ProposalStatus | None = None,
    ) -> builtins.list[Proposal]:
        return await self._proposals.list(
            tenant_id,
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            status=status,
        )

    async def update_section(
        self,
        tenant_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        kind: ProposalSectionKind,
        content: str,
    ) -> Proposal | None:
        proposal = await self._proposals.get(tenant_id, proposal_id)
        if proposal is None:
            return None
        for section in proposal.sections:
            if section.kind is kind:
                section.content = content
                break
        else:  # pragma: no cover - sections are always scaffolded complete
            proposal.sections.append(
                ProposalSection(
                    kind=kind,
                    title=PROPOSAL_SECTION_TITLES[kind],
                    content=content,
                    order=len(proposal.sections),
                )
            )
        updated = await self._proposals.update(proposal)
        await self._events.record(
            event_type=PMEventType.PROPOSAL_SECTION_UPDATED,
            tenant_id=tenant_id,
            aggregate_id=proposal_id,
            payload={"section": kind.value},
        )
        return updated

    async def mark_ready(
        self,
        tenant_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        approved_by: str | None = None,
    ) -> Proposal:
        """Promote a complete proposal to READY.

        Raises if the proposal is incomplete, or if it requires approval and no
        approver was supplied — autonomy never sends an unapproved high-value
        proposal.
        """
        proposal = await self._proposals.get(tenant_id, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        if not proposal.is_complete:
            raise ValueError("proposal is incomplete; all eleven sections must be filled")
        if proposal.requires_approval and approved_by is None:
            raise ValueError("proposal value requires human approval before it is ready")
        proposal.status = ProposalStatus.READY
        proposal.approved_by = approved_by
        updated = await self._proposals.update(proposal)
        if updated is None:  # pragma: no cover - fetched above within the same session
            raise ValueError("proposal not found")
        await self._events.record(
            event_type=PMEventType.PROPOSAL_READY,
            tenant_id=tenant_id,
            aggregate_id=proposal_id,
            payload={"approved_by": approved_by or ""},
        )
        return updated

    async def send(self, tenant_id: uuid.UUID, proposal_id: uuid.UUID) -> Proposal:
        proposal = await self._proposals.get(tenant_id, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        if proposal.status is not ProposalStatus.READY:
            raise ValueError("only a READY proposal can be sent")
        proposal.status = ProposalStatus.SENT
        updated = await self._proposals.update(proposal)
        if updated is None:  # pragma: no cover
            raise ValueError("proposal not found")
        await self._events.record(
            event_type=PMEventType.PROPOSAL_SENT,
            tenant_id=tenant_id,
            aggregate_id=proposal_id,
            payload={},
        )
        return updated

    async def record_decision(
        self, tenant_id: uuid.UUID, proposal_id: uuid.UUID, *, accepted: bool
    ) -> Proposal | None:
        proposal = await self._proposals.get(tenant_id, proposal_id)
        if proposal is None:
            return None
        proposal.status = ProposalStatus.ACCEPTED if accepted else ProposalStatus.REJECTED
        updated = await self._proposals.update(proposal)
        await self._events.record(
            event_type=(
                PMEventType.PROPOSAL_ACCEPTED if accepted else PMEventType.PROPOSAL_REJECTED
            ),
            tenant_id=tenant_id,
            aggregate_id=proposal_id,
            payload={},
        )
        return updated
