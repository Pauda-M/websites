"""Repositories for semantic memory: versioned items and typed relationships."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from pb_api.cognitive.db.models import RelationshipRow, SemanticItemRow
from pb_api.cognitive.domain.semantic import KnowledgeKind, Relationship, SemanticItem
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_item(row: SemanticItemRow) -> SemanticItem:
    return SemanticItem(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=KnowledgeKind(row.kind),
        name=row.name,
        content=row.content,
        confidence=row.confidence,
        source=row.source,
        version=row.version,
        superseded_by=row.superseded_by,
        embedding=list(row.embedding) if row.embedding is not None else None,
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


def _row_to_relationship(row: RelationshipRow) -> Relationship:
    return Relationship(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        target_id=row.target_id,
        relation=row.relation,
        confidence=row.confidence,
        source=row.source,
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class SemanticRepository(BaseRepository):
    async def add_item(self, item: SemanticItem) -> SemanticItem:
        row = SemanticItemRow(
            id=item.id,
            tenant_id=item.tenant_id,
            kind=item.kind.value,
            name=item.name,
            content=item.content,
            confidence=item.confidence,
            source=item.source,
            version=item.version,
            superseded_by=item.superseded_by,
            embedding=item.embedding,
            meta=item.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_item(row)

    async def get_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> SemanticItem | None:
        row = await self.session.get(SemanticItemRow, item_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_item(row)

    async def list_items(
        self,
        tenant_id: uuid.UUID,
        *,
        kind: KnowledgeKind | None = None,
        include_superseded: bool = False,
        limit: int = 100,
    ) -> list[SemanticItem]:
        stmt = select(SemanticItemRow).where(SemanticItemRow.tenant_id == tenant_id)
        if kind is not None:
            stmt = stmt.where(SemanticItemRow.kind == kind.value)
        if not include_superseded:
            stmt = stmt.where(SemanticItemRow.superseded_by.is_(None))
        stmt = stmt.order_by(SemanticItemRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_item(row) for row in rows]

    async def supersede(
        self, tenant_id: uuid.UUID, old_id: uuid.UUID, new_item: SemanticItem
    ) -> SemanticItem | None:
        old = await self.session.get(SemanticItemRow, old_id)
        if old is None or old.tenant_id != tenant_id:
            return None
        new_row = SemanticItemRow(
            id=new_item.id,
            tenant_id=new_item.tenant_id,
            kind=new_item.kind.value,
            name=new_item.name,
            content=new_item.content,
            confidence=new_item.confidence,
            source=new_item.source,
            version=old.version + 1,
            superseded_by=None,
            embedding=new_item.embedding,
            meta=new_item.metadata,
        )
        self.session.add(new_row)
        old.superseded_by = new_row.id
        await self.session.flush()
        return _row_to_item(new_row)

    async def add_relationship(self, rel: Relationship) -> Relationship:
        row = RelationshipRow(
            id=rel.id,
            tenant_id=rel.tenant_id,
            source_id=rel.source_id,
            target_id=rel.target_id,
            relation=rel.relation,
            confidence=rel.confidence,
            source=rel.source,
            meta=rel.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_relationship(row)

    async def list_relationships(
        self,
        tenant_id: uuid.UUID,
        *,
        source_id: uuid.UUID | None = None,
        target_id: uuid.UUID | None = None,
        relation: str | None = None,
        limit: int = 200,
    ) -> list[Relationship]:
        stmt = select(RelationshipRow).where(RelationshipRow.tenant_id == tenant_id)
        if source_id is not None:
            stmt = stmt.where(RelationshipRow.source_id == source_id)
        if target_id is not None:
            stmt = stmt.where(RelationshipRow.target_id == target_id)
        if relation is not None:
            stmt = stmt.where(RelationshipRow.relation == relation)
        stmt = stmt.order_by(RelationshipRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_relationship(row) for row in rows]

    async def neighbors(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> list[Relationship]:
        stmt = (
            select(RelationshipRow)
            .where(RelationshipRow.tenant_id == tenant_id)
            .where(
                or_(
                    RelationshipRow.source_id == entity_id,
                    RelationshipRow.target_id == entity_id,
                )
            )
            .order_by(RelationshipRow.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_relationship(row) for row in rows]
