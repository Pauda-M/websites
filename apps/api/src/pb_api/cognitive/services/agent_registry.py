"""Agent Registry: register and manage AI Employees.

Every agent registers identity, role, capabilities, authority, tools, memory
access, goals, policies, status, and version (Phase 7 spec). Names are unique
per tenant; re-registering an existing name updates it and bumps the version.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.agents import AgentRegistration, AgentStatus
from pb_api.cognitive.domain.common import AuthorityLevel, MemoryType
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.repositories.agents import AgentRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class AgentRegistry:
    def __init__(self, repository: AgentRepository, events: EventProcessor) -> None:
        self._repo = repository
        self._events = events

    async def register(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        role: str,
        capabilities: list[str] | None = None,
        default_authority: AuthorityLevel = AuthorityLevel.SUGGEST,
        tools: list[str] | None = None,
        memory_access: list[MemoryType] | None = None,
        goal_ids: list[uuid.UUID] | None = None,
        policy_ids: list[uuid.UUID] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentRegistration:
        existing = await self._repo.get_by_name(tenant_id, name)
        if existing is not None:
            existing.role = role
            existing.capabilities = (
                capabilities if capabilities is not None else existing.capabilities
            )
            existing.default_authority = default_authority
            existing.tools = tools if tools is not None else existing.tools
            existing.memory_access = (
                memory_access if memory_access is not None else existing.memory_access
            )
            existing.goal_ids = goal_ids if goal_ids is not None else existing.goal_ids
            existing.policy_ids = policy_ids if policy_ids is not None else existing.policy_ids
            existing.metadata = metadata if metadata is not None else existing.metadata
            existing.version += 1
            updated = await self._repo.update(existing)
            if updated is None:  # pragma: no cover - existing was just fetched
                raise RuntimeError("agent update failed after fetch")
            await self._events.record(
                event_type=EventType.AGENT_REGISTERED,
                tenant_id=tenant_id,
                aggregate_id=updated.id,
                payload={"name": name, "version": updated.version},
            )
            return updated

        agent = AgentRegistration(
            tenant_id=tenant_id,
            name=name,
            role=role,
            capabilities=capabilities or [],
            default_authority=default_authority,
            tools=tools or [],
            memory_access=memory_access or [MemoryType.WORKING, MemoryType.EPISODIC],
            goal_ids=goal_ids or [],
            policy_ids=policy_ids or [],
            metadata=metadata or {},
        )
        stored = await self._repo.add(agent)
        await self._events.record(
            event_type=EventType.AGENT_REGISTERED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"name": name, "version": 1},
        )
        return stored

    async def get(self, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> AgentRegistration | None:
        return await self._repo.get(tenant_id, agent_id)

    async def get_by_name(self, tenant_id: uuid.UUID, name: str) -> AgentRegistration | None:
        return await self._repo.get_by_name(tenant_id, name)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        role: str | None = None,
        status: AgentStatus | None = None,
    ) -> list[AgentRegistration]:
        return await self._repo.list(tenant_id, role=role, status=status)

    async def set_status(
        self, tenant_id: uuid.UUID, agent_id: uuid.UUID, status: AgentStatus
    ) -> AgentRegistration | None:
        agent = await self._repo.get(tenant_id, agent_id)
        if agent is None:
            return None
        agent.status = status
        updated = await self._repo.update(agent)
        await self._events.record(
            event_type=EventType.AGENT_STATUS_CHANGED,
            tenant_id=tenant_id,
            aggregate_id=agent_id,
            payload={"status": status.value},
        )
        return updated
