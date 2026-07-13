"""Procedural memory service: reusable, executable workflow definitions.

Ships the Phase 7 example procedures (Lead Qualification, Proposal Creation,
Project Kickoff, Customer Follow-up, Support Ticket) as real, seedable templates.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.procedural import Procedure, ProcedureStep
from pb_api.cognitive.repositories.procedural import ProcedureRepository
from pb_api.cognitive.services.event_processor import EventProcessor


def _default_procedure_templates() -> list[Procedure]:
    """The reusable example workflows named in the specification.

    ``tenant_id`` is filled in when seeded for a specific tenant.
    """
    placeholder = uuid.UUID(int=0)
    return [
        Procedure(
            tenant_id=placeholder,
            slug="lead-qualification",
            name="Lead Qualification",
            description="Qualify an inbound lead against ICP and budget.",
            steps=[
                ProcedureStep(key="enrich", title="Enrich lead", capability="crm.enrich_lead"),
                ProcedureStep(
                    key="score",
                    title="Score fit",
                    capability="crm.score_lead",
                    depends_on=["enrich"],
                ),
                ProcedureStep(
                    key="route",
                    title="Route or disqualify",
                    capability="crm.route_lead",
                    depends_on=["score"],
                ),
            ],
        ),
        Procedure(
            tenant_id=placeholder,
            slug="proposal-creation",
            name="Proposal Creation",
            description="Draft, review, and send a proposal.",
            steps=[
                ProcedureStep(key="draft", title="Draft proposal", capability="proposal.draft"),
                ProcedureStep(
                    key="review",
                    title="Human review",
                    depends_on=["draft"],
                    requires_approval=True,
                ),
                ProcedureStep(
                    key="send",
                    title="Send proposal",
                    capability="proposal.send",
                    depends_on=["review"],
                ),
            ],
        ),
        Procedure(
            tenant_id=placeholder,
            slug="project-kickoff",
            name="Project Kickoff",
            description="Kick off a newly won project.",
            steps=[
                ProcedureStep(
                    key="workspace", title="Create workspace", capability="portal.create_workspace"
                ),
                ProcedureStep(
                    key="plan",
                    title="Draft project plan",
                    capability="pm.draft_plan",
                    depends_on=["workspace"],
                ),
                ProcedureStep(
                    key="invite",
                    title="Invite stakeholders",
                    capability="portal.invite",
                    depends_on=["workspace"],
                ),
            ],
        ),
        Procedure(
            tenant_id=placeholder,
            slug="customer-follow-up",
            name="Customer Follow-up",
            description="Follow up with a customer after an interaction.",
            steps=[
                ProcedureStep(key="assess", title="Assess health", capability="crm.assess_health"),
                ProcedureStep(
                    key="compose",
                    title="Compose follow-up",
                    capability="comms.compose",
                    depends_on=["assess"],
                ),
                ProcedureStep(
                    key="approve",
                    title="Approve before first contact",
                    depends_on=["compose"],
                    requires_approval=True,
                ),
            ],
        ),
        Procedure(
            tenant_id=placeholder,
            slug="support-ticket",
            name="Support Ticket",
            description="Triage and resolve a support ticket.",
            steps=[
                ProcedureStep(key="triage", title="Triage ticket", capability="support.triage"),
                ProcedureStep(
                    key="resolve",
                    title="Resolve or escalate",
                    capability="support.resolve",
                    depends_on=["triage"],
                ),
                ProcedureStep(
                    key="close",
                    title="Close and summarise",
                    capability="support.close",
                    depends_on=["resolve"],
                ),
            ],
        ),
    ]


class ProceduralMemoryService:
    def __init__(self, repository: ProcedureRepository, events: EventProcessor) -> None:
        self._repo = repository
        self._events = events

    async def register(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        description: str = "",
        steps: list[ProcedureStep] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Procedure:
        existing = await self._repo.get_by_slug(tenant_id, slug)
        version = (existing.version + 1) if existing is not None else 1
        procedure = Procedure(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            description=description,
            version=version,
            steps=steps or [],
            metadata=metadata or {},
        )
        stored = await self._repo.add(procedure)
        await self._events.record(
            event_type=EventType.WORKFLOW_PROCEDURE_REGISTERED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"slug": slug, "version": version},
        )
        return stored

    async def seed_defaults(self, tenant_id: uuid.UUID) -> list[Procedure]:
        """Register the example procedures for a tenant that has none of them."""
        created: list[Procedure] = []
        for template in _default_procedure_templates():
            if await self._repo.get_by_slug(tenant_id, template.slug) is not None:
                continue
            created.append(
                await self.register(
                    tenant_id=tenant_id,
                    slug=template.slug,
                    name=template.name,
                    description=template.description,
                    steps=template.steps,
                )
            )
        return created

    async def get_by_slug(self, tenant_id: uuid.UUID, slug: str) -> Procedure | None:
        return await self._repo.get_by_slug(tenant_id, slug)

    async def list(self, tenant_id: uuid.UUID, limit: int = 100) -> list[Procedure]:
        return await self._repo.list(tenant_id, limit=limit)
