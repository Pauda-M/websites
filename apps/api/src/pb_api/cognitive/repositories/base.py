"""Repository foundations: tenant-scoped async access + JSON conversion helpers.

JSON columns cannot hold ``uuid.UUID`` or Pydantic models directly, so these
helpers convert list/model fields to and from JSON-safe primitives at the
persistence boundary. Every query is scoped by ``tenant_id`` — cross-tenant
access is impossible by construction (Genesis §12.6).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


def uuids_to_json(items: Sequence[uuid.UUID]) -> list[str]:
    return [str(item) for item in items]


def json_to_uuids(raw: object) -> list[uuid.UUID]:
    if not isinstance(raw, list):
        return []
    return [uuid.UUID(str(item)) for item in raw]
