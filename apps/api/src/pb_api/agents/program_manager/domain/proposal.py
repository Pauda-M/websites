"""Proposal domain — the eleven-section proposal the Program Manager prepares.

A proposal is an ordered set of :class:`ProposalSection` blocks whose kinds are
drawn from the canonical eleven-section structure (:class:`ProposalSectionKind`).
The Program Manager prepares proposals as drafts; whether one may progress to
``READY``/``SENT`` autonomously is gated by authority and the configured value
threshold (see the application layer), never decided here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.agents.program_manager.domain.common import new_id, utcnow


class ProposalSectionKind(enum.StrEnum):
    """The eleven canonical proposal sections, in presentation order."""

    EXECUTIVE_SUMMARY = "executive_summary"
    UNDERSTANDING = "understanding"
    OBJECTIVES = "objectives"
    PROPOSED_SOLUTION = "proposed_solution"
    SCOPE_OF_WORK = "scope_of_work"
    TIMELINE = "timeline"
    TEAM = "team"
    PRICING = "pricing"
    TERMS = "terms"
    WHY_US = "why_us"
    NEXT_STEPS = "next_steps"


# Canonical order + default human titles for the eleven sections.
PROPOSAL_SECTION_ORDER: tuple[ProposalSectionKind, ...] = (
    ProposalSectionKind.EXECUTIVE_SUMMARY,
    ProposalSectionKind.UNDERSTANDING,
    ProposalSectionKind.OBJECTIVES,
    ProposalSectionKind.PROPOSED_SOLUTION,
    ProposalSectionKind.SCOPE_OF_WORK,
    ProposalSectionKind.TIMELINE,
    ProposalSectionKind.TEAM,
    ProposalSectionKind.PRICING,
    ProposalSectionKind.TERMS,
    ProposalSectionKind.WHY_US,
    ProposalSectionKind.NEXT_STEPS,
)

PROPOSAL_SECTION_TITLES: dict[ProposalSectionKind, str] = {
    ProposalSectionKind.EXECUTIVE_SUMMARY: "Executive Summary",
    ProposalSectionKind.UNDERSTANDING: "Understanding of Your Needs",
    ProposalSectionKind.OBJECTIVES: "Objectives",
    ProposalSectionKind.PROPOSED_SOLUTION: "Proposed Solution",
    ProposalSectionKind.SCOPE_OF_WORK: "Scope of Work & Deliverables",
    ProposalSectionKind.TIMELINE: "Timeline & Milestones",
    ProposalSectionKind.TEAM: "Team & Roles",
    ProposalSectionKind.PRICING: "Pricing & Investment",
    ProposalSectionKind.TERMS: "Terms & Assumptions",
    ProposalSectionKind.WHY_US: "Why Us",
    ProposalSectionKind.NEXT_STEPS: "Next Steps",
}


class ProposalStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    READY = "ready"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ProposalSection(BaseModel):
    """One section of a proposal."""

    kind: ProposalSectionKind
    title: str
    content: str = ""
    order: int = Field(default=0, ge=0)


class Proposal(BaseModel):
    """A versioned, eleven-section proposal for an Opportunity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    title: str
    status: ProposalStatus = ProposalStatus.DRAFT
    version: int = Field(default=1, ge=1)
    sections: list[ProposalSection] = Field(default_factory=list)
    total_value: float = Field(default=0.0, ge=0.0)
    currency: str = "EUR"
    valid_until: date | None = None
    requires_approval: bool = False
    approved_by: str | None = None
    owner_agent_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def is_complete(self) -> bool:
        """True when all eleven canonical sections are present and non-empty."""
        present = {section.kind for section in self.sections if section.content.strip()}
        return present >= set(PROPOSAL_SECTION_ORDER)
