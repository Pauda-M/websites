"""Tool Registry: every tool exposes name, version, permissions, inputs,
outputs, health, and timeout (Phase 7 spec)."""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.tools import SideEffect, ToolDefinition, ToolHealth
from pb_api.cognitive.repositories.tools import ToolRepository


class ToolRegistry:
    def __init__(self, repository: ToolRepository) -> None:
        self._repo = repository

    async def register(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        permissions: list[str] | None = None,
        input_schema: dict[str, object] | None = None,
        output_schema: dict[str, object] | None = None,
        side_effect: SideEffect = SideEffect.READ_ONLY,
        timeout_seconds: int = 30,
        metadata: dict[str, object] | None = None,
    ) -> ToolDefinition:
        existing = await self._repo.get_by_name(tenant_id, name)
        if existing is not None:
            existing.version = version
            existing.description = description
            existing.permissions = permissions or []
            existing.input_schema = input_schema or {}
            existing.output_schema = output_schema or {}
            existing.side_effect = side_effect
            existing.timeout_seconds = timeout_seconds
            existing.metadata = metadata or {}
            updated = await self._repo.update(existing)
            if updated is None:  # pragma: no cover - existing was just fetched
                raise RuntimeError("tool update failed after fetch")
            return updated

        tool = ToolDefinition(
            tenant_id=tenant_id,
            name=name,
            version=version,
            description=description,
            permissions=permissions or [],
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            side_effect=side_effect,
            timeout_seconds=timeout_seconds,
            health=ToolHealth.UNKNOWN,
            metadata=metadata or {},
        )
        return await self._repo.add(tool)

    async def get(self, tenant_id: uuid.UUID, tool_id: uuid.UUID) -> ToolDefinition | None:
        return await self._repo.get(tenant_id, tool_id)

    async def get_by_name(self, tenant_id: uuid.UUID, name: str) -> ToolDefinition | None:
        return await self._repo.get_by_name(tenant_id, name)

    async def list(self, tenant_id: uuid.UUID) -> list[ToolDefinition]:
        return await self._repo.list(tenant_id)

    async def set_health(
        self, tenant_id: uuid.UUID, tool_id: uuid.UUID, health: ToolHealth
    ) -> ToolDefinition | None:
        return await self._repo.set_health(tenant_id, tool_id, health)
