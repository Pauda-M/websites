"""Policy Engine.

Deterministic evaluation: among enabled policies matching the action and
resource, the most specific + highest-priority rule wins; ties resolve
deny-over-approval-over-allow. An ALLOW whose ``min_authority`` exceeds the
actor's authority is escalated to REQUIRE_APPROVAL — autonomy never silently
exceeds its bound. With no matching policy the engine denies (secure by default).
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.policy import (
    Policy,
    PolicyDecision,
    PolicyEffect,
    PolicyRequest,
)
from pb_api.cognitive.repositories.policy import PolicyRepository


def _matches(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return pattern == value


def _specificity(pattern: str) -> int:
    return 0 if pattern == "*" else len(pattern.rstrip("*"))


_EFFECT_PRECEDENCE = {
    PolicyEffect.DENY: 3,
    PolicyEffect.REQUIRE_APPROVAL: 2,
    PolicyEffect.ALLOW: 1,
}


class PolicyEngine:
    def __init__(self, repository: PolicyRepository) -> None:
        self._repo = repository

    async def add_policy(self, policy: Policy) -> Policy:
        return await self._repo.add(policy)

    async def list_policies(
        self, tenant_id: uuid.UUID, *, enabled_only: bool = True
    ) -> list[Policy]:
        return await self._repo.list(tenant_id, enabled_only=enabled_only)

    async def remove_policy(self, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> bool:
        return await self._repo.delete(tenant_id, policy_id)

    async def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        policies = await self._repo.list(request.tenant_id, enabled_only=True)
        candidates = [
            policy
            for policy in policies
            if _matches(policy.action, request.action)
            and _matches(policy.resource, request.resource)
        ]
        if not candidates:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                effect=PolicyEffect.DENY,
                reason="No matching policy; default deny.",
                matched_policy_id=None,
            )

        def rank(policy: Policy) -> tuple[int, int, int]:
            return (policy.priority, _specificity(policy.action), _specificity(policy.resource))

        best_rank = max(rank(policy) for policy in candidates)
        top = [policy for policy in candidates if rank(policy) == best_rank]
        winner = max(top, key=lambda policy: _EFFECT_PRECEDENCE[policy.effect])

        if winner.effect is PolicyEffect.DENY:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                effect=PolicyEffect.DENY,
                reason=f"Denied by policy '{winner.name}'.",
                matched_policy_id=winner.id,
            )
        if winner.effect is PolicyEffect.REQUIRE_APPROVAL:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason=f"Policy '{winner.name}' requires approval.",
                matched_policy_id=winner.id,
            )
        # ALLOW — but gate on authority.
        if request.actor_authority < winner.min_authority:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason=(
                    f"Policy '{winner.name}' allows the action, but actor authority "
                    f"{int(request.actor_authority)} is below required "
                    f"{int(winner.min_authority)}; approval required."
                ),
                matched_policy_id=winner.id,
            )
        return PolicyDecision(
            allowed=True,
            requires_approval=False,
            effect=PolicyEffect.ALLOW,
            reason=f"Allowed by policy '{winner.name}'.",
            matched_policy_id=winner.id,
        )
