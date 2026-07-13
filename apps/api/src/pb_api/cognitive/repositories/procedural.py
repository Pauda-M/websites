"""Repository for procedural memory: reusable workflow definitions."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import ProcedureRow
from pb_api.cognitive.domain.procedural import Procedure, ProcedureStep
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_procedure(row: ProcedureRow) -> Procedure:
    return Procedure(
        id=row.id,
        tenant_id=row.tenant_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        version=row.version,
        steps=[ProcedureStep.model_validate(step) for step in row.steps],
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class ProcedureRepository(BaseRepository):
    async def add(self, proc: Procedure) -> Procedure:
        row = ProcedureRow(
            id=proc.id,
            tenant_id=proc.tenant_id,
            slug=proc.slug,
            name=proc.name,
            description=proc.description,
            version=proc.version,
            steps=[step.model_dump(mode="json") for step in proc.steps],
            meta=proc.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_procedure(row)

    async def get(self, tenant_id: uuid.UUID, proc_id: uuid.UUID) -> Procedure | None:
        row = await self.session.get(ProcedureRow, proc_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_procedure(row)

    async def get_by_slug(self, tenant_id: uuid.UUID, slug: str) -> Procedure | None:
        stmt = (
            select(ProcedureRow)
            .where(ProcedureRow.tenant_id == tenant_id, ProcedureRow.slug == slug)
            .order_by(ProcedureRow.version.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return _row_to_procedure(row)

    async def list(self, tenant_id: uuid.UUID, limit: int = 100) -> list[Procedure]:
        stmt = (
            select(ProcedureRow)
            .where(ProcedureRow.tenant_id == tenant_id)
            .order_by(ProcedureRow.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_procedure(row) for row in rows]
