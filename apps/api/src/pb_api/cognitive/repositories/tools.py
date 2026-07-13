"""Repository for the tool registry."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import ToolRow
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.domain.tools import SideEffect, ToolDefinition, ToolHealth
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_tool(row: ToolRow) -> ToolDefinition:
    return ToolDefinition(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        version=row.version,
        description=row.description,
        permissions=[str(item) for item in row.permissions],
        input_schema=dict(row.input_schema),
        output_schema=dict(row.output_schema),
        side_effect=SideEffect(row.side_effect),
        timeout_seconds=row.timeout_seconds,
        health=ToolHealth(row.health),
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ToolRepository(BaseRepository):
    async def add(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.tenant_id is None:
            raise ValueError("tool requires tenant_id")
        row = ToolRow(
            id=tool.id,
            tenant_id=tool.tenant_id,
            name=tool.name,
            version=tool.version,
            description=tool.description,
            permissions=list(tool.permissions),
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            side_effect=tool.side_effect.value,
            timeout_seconds=tool.timeout_seconds,
            health=tool.health.value,
            meta=tool.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_tool(row)

    async def get(self, tenant_id: uuid.UUID, tool_id: uuid.UUID) -> ToolDefinition | None:
        row = await self.session.get(ToolRow, tool_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_tool(row)

    async def get_by_name(self, tenant_id: uuid.UUID, name: str) -> ToolDefinition | None:
        stmt = select(ToolRow).where(ToolRow.tenant_id == tenant_id, ToolRow.name == name).limit(1)
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return _row_to_tool(row)

    async def list(self, tenant_id: uuid.UUID, *, limit: int = 200) -> list[ToolDefinition]:
        stmt = (
            select(ToolRow)
            .where(ToolRow.tenant_id == tenant_id)
            .order_by(ToolRow.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_tool(row) for row in rows]

    async def update(self, tool: ToolDefinition) -> ToolDefinition | None:
        row = await self.session.get(ToolRow, tool.id)
        if row is None or row.tenant_id != tool.tenant_id:
            return None
        row.version = tool.version
        row.description = tool.description
        row.permissions = list(tool.permissions)
        row.input_schema = tool.input_schema
        row.output_schema = tool.output_schema
        row.side_effect = tool.side_effect.value
        row.timeout_seconds = tool.timeout_seconds
        row.health = tool.health.value
        row.meta = tool.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_tool(row)

    async def set_health(
        self, tenant_id: uuid.UUID, tool_id: uuid.UUID, health: ToolHealth
    ) -> ToolDefinition | None:
        row = await self.session.get(ToolRow, tool_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        row.health = health.value
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_tool(row)
