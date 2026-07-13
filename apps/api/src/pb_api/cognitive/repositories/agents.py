"""Repository for the agent registry (AI Employee registrations)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import AgentRow
from pb_api.cognitive.domain.agents import AgentRegistration, AgentStatus
from pb_api.cognitive.domain.common import AuthorityLevel, MemoryType, utcnow
from pb_api.cognitive.repositories.base import (
    BaseRepository,
    json_to_uuids,
    uuids_to_json,
)


def _row_to_agent(row: AgentRow) -> AgentRegistration:
    return AgentRegistration(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        role=row.role,
        capabilities=[str(item) for item in row.capabilities],
        default_authority=AuthorityLevel(row.default_authority),
        tools=[str(item) for item in row.tools],
        memory_access=[MemoryType(str(item)) for item in row.memory_access],
        goal_ids=json_to_uuids(row.goal_ids),
        policy_ids=json_to_uuids(row.policy_ids),
        status=AgentStatus(row.status),
        version=row.version,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentRepository(BaseRepository):
    async def add(self, agent: AgentRegistration) -> AgentRegistration:
        row = AgentRow(
            id=agent.id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            role=agent.role,
            capabilities=list(agent.capabilities),
            default_authority=int(agent.default_authority),
            tools=list(agent.tools),
            memory_access=[item.value for item in agent.memory_access],
            goal_ids=uuids_to_json(agent.goal_ids),
            policy_ids=uuids_to_json(agent.policy_ids),
            status=agent.status.value,
            version=agent.version,
            meta=agent.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_agent(row)

    async def get(self, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> AgentRegistration | None:
        row = await self.session.get(AgentRow, agent_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_agent(row)

    async def get_by_name(self, tenant_id: uuid.UUID, name: str) -> AgentRegistration | None:
        stmt = (
            select(AgentRow).where(AgentRow.tenant_id == tenant_id, AgentRow.name == name).limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return _row_to_agent(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        role: str | None = None,
        status: AgentStatus | None = None,
        limit: int = 200,
    ) -> list[AgentRegistration]:
        stmt = select(AgentRow).where(AgentRow.tenant_id == tenant_id)
        if role is not None:
            stmt = stmt.where(AgentRow.role == role)
        if status is not None:
            stmt = stmt.where(AgentRow.status == status.value)
        stmt = stmt.order_by(AgentRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_agent(row) for row in rows]

    async def update(self, agent: AgentRegistration) -> AgentRegistration | None:
        row = await self.session.get(AgentRow, agent.id)
        if row is None or row.tenant_id != agent.tenant_id:
            return None
        row.name = agent.name
        row.role = agent.role
        row.capabilities = list(agent.capabilities)
        row.default_authority = int(agent.default_authority)
        row.tools = list(agent.tools)
        row.memory_access = [item.value for item in agent.memory_access]
        row.goal_ids = list(uuids_to_json(agent.goal_ids))
        row.policy_ids = list(uuids_to_json(agent.policy_ids))
        row.status = agent.status.value
        row.version = agent.version
        row.meta = agent.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_agent(row)
