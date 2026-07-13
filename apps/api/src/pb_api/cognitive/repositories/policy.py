"""Repository for policy rules."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import PolicyRow
from pb_api.cognitive.domain.common import AuthorityLevel
from pb_api.cognitive.domain.policy import Policy, PolicyEffect
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_policy(row: PolicyRow) -> Policy:
    return Policy(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        action=row.action,
        resource=row.resource,
        effect=PolicyEffect(row.effect),
        min_authority=AuthorityLevel(row.min_authority),
        priority=row.priority,
        enabled=row.enabled,
        description=row.description,
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class PolicyRepository(BaseRepository):
    async def add(self, policy: Policy) -> Policy:
        row = PolicyRow(
            id=policy.id,
            tenant_id=policy.tenant_id,
            name=policy.name,
            action=policy.action,
            resource=policy.resource,
            effect=policy.effect.value,
            min_authority=int(policy.min_authority),
            priority=policy.priority,
            enabled=policy.enabled,
            description=policy.description,
            meta=policy.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_policy(row)

    async def get(self, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> Policy | None:
        row = await self.session.get(PolicyRow, policy_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_policy(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        enabled_only: bool = True,
        limit: int = 500,
    ) -> list[Policy]:
        stmt = select(PolicyRow).where(PolicyRow.tenant_id == tenant_id)
        if enabled_only:
            stmt = stmt.where(PolicyRow.enabled.is_(True))
        stmt = stmt.order_by(PolicyRow.priority.desc(), PolicyRow.created_at.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_policy(row) for row in rows]

    async def update(self, policy: Policy) -> Policy | None:
        row = await self.session.get(PolicyRow, policy.id)
        if row is None or row.tenant_id != policy.tenant_id:
            return None
        row.name = policy.name
        row.action = policy.action
        row.resource = policy.resource
        row.effect = policy.effect.value
        row.min_authority = int(policy.min_authority)
        row.priority = policy.priority
        row.enabled = policy.enabled
        row.description = policy.description
        row.meta = policy.metadata
        await self.session.flush()
        return _row_to_policy(row)

    async def delete(self, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> bool:
        row = await self.session.get(PolicyRow, policy_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
