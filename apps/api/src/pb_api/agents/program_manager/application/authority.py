"""Authority — the Program Manager's governed-autonomy boundary.

The Program Manager operates at one of three coarse tiers (L0/L1/L2). This module
maps those tiers onto the Cognitive Core's fine-grained A0-A5 authority levels and
delegates the actual decision to the Core's deterministic
:class:`~pb_api.cognitive.services.policy_engine.PolicyEngine` — the Program
Manager never re-implements policy evaluation. It also owns the canonical
catalogue of Program-Manager action strings and seeds a default, tenant-scoped
policy set so autonomy is bounded from first boot (secure by default).

Mapping (L → A):
  * ``OBSERVE_ONLY``     → ``OBSERVE``            (read/draft only)
  * ``ACT_WITH_APPROVAL``→ ``ACT_WITH_APPROVAL``  (reversible internal actions)
  * ``ACT_BOUNDED``      → ``ACT_BOUNDED``        (bounded outward actions)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pb_api.agents.program_manager.domain.common import AuthorityLevel, PMAuthorityLevel
from pb_api.cognitive.domain.policy import Policy, PolicyDecision, PolicyEffect, PolicyRequest
from pb_api.cognitive.services.policy_engine import PolicyEngine

# Coarse PM tiers → fine Cognitive Core levels.
PM_AUTHORITY_TO_COGNITIVE: dict[PMAuthorityLevel, AuthorityLevel] = {
    PMAuthorityLevel.OBSERVE_ONLY: AuthorityLevel.OBSERVE,
    PMAuthorityLevel.ACT_WITH_APPROVAL: AuthorityLevel.ACT_WITH_APPROVAL,
    PMAuthorityLevel.ACT_BOUNDED: AuthorityLevel.ACT_BOUNDED,
}


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """A canonical Program-Manager action and the authority it requires."""

    action: str
    description: str
    min_authority: PMAuthorityLevel


# The canonical catalogue of Program-Manager actions. Internal, reversible
# actions require L1; outward-facing or externally-committing actions require L2;
# reading and escalation are always permitted (L0).
ACTION_CATALOG: tuple[ActionSpec, ...] = (
    ActionSpec("crm.read", "Read CRM records", PMAuthorityLevel.OBSERVE_ONLY),
    ActionSpec("crm.create", "Create a CRM record", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec("crm.update", "Update a CRM record", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec("task.create", "Create an internal task", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec("note.create", "Record an internal note", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec("schedule.create", "Schedule a follow-up", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec("proposal.draft", "Prepare a proposal draft", PMAuthorityLevel.ACT_WITH_APPROVAL),
    ActionSpec(
        "opportunity.advance",
        "Advance an opportunity between open stages",
        PMAuthorityLevel.ACT_WITH_APPROVAL,
    ),
    ActionSpec(
        "communication.send",
        "Send a message to a customer",
        PMAuthorityLevel.ACT_BOUNDED,
    ),
    ActionSpec("meeting.book", "Book a meeting with a customer", PMAuthorityLevel.ACT_BOUNDED),
    ActionSpec("proposal.send", "Send a proposal to a customer", PMAuthorityLevel.ACT_BOUNDED),
    ActionSpec("opportunity.close", "Close an opportunity won/lost", PMAuthorityLevel.ACT_BOUNDED),
    ActionSpec("issue.escalate", "Escalate an issue to a human", PMAuthorityLevel.OBSERVE_ONLY),
)

_CATALOG_BY_ACTION: dict[str, ActionSpec] = {spec.action: spec for spec in ACTION_CATALOG}

# Policy names the Program Manager seeds; used to keep seeding idempotent.
_SEED_POLICY_PREFIX = "pm-default:"


def required_authority(action: str) -> PMAuthorityLevel:
    """The minimum PM tier for ``action``; unknown actions require the top tier."""
    spec = _CATALOG_BY_ACTION.get(action)
    return spec.min_authority if spec is not None else PMAuthorityLevel.ACT_BOUNDED


class AuthorityService:
    """Decides whether the Program Manager may take an action, via the Core engine."""

    def __init__(self, policies: PolicyEngine) -> None:
        self._policies = policies

    @staticmethod
    def to_cognitive(level: PMAuthorityLevel) -> AuthorityLevel:
        return PM_AUTHORITY_TO_COGNITIVE[level]

    async def seed_default_policies(self, tenant_id: uuid.UUID) -> list[Policy]:
        """Idempotently install the default PM policy set for a tenant.

        One ALLOW policy per catalogue action, gated at the action's required
        authority. The Cognitive Core escalates an ALLOW to REQUIRE_APPROVAL when
        the actor's authority is below the policy's ``min_authority`` — so a
        single ALLOW rule expresses "permitted at or above this tier, approval
        below it".
        """
        existing = {
            policy.name
            for policy in await self._policies.list_policies(tenant_id, enabled_only=False)
        }
        created: list[Policy] = []
        for spec in ACTION_CATALOG:
            name = f"{_SEED_POLICY_PREFIX}{spec.action}"
            if name in existing:
                continue
            policy = await self._policies.add_policy(
                Policy(
                    tenant_id=tenant_id,
                    name=name,
                    action=spec.action,
                    effect=PolicyEffect.ALLOW,
                    min_authority=self.to_cognitive(spec.min_authority),
                    priority=100,
                    description=spec.description,
                )
            )
            created.append(policy)
        return created

    async def authorize(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_level: PMAuthorityLevel,
        action: str,
        resource: str = "*",
    ) -> PolicyDecision:
        """Evaluate an action for an actor at ``actor_level`` against tenant policy."""
        return await self._policies.evaluate(
            PolicyRequest(
                tenant_id=tenant_id,
                actor_authority=self.to_cognitive(actor_level),
                action=action,
                resource=resource,
            )
        )
