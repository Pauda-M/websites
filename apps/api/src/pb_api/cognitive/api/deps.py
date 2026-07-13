"""Cognitive API dependencies: a per-request CognitiveCore bound to a session.

Reuses the platform's DB session dependency (`pb_api.api.deps.get_db_session`)
so the cognitive core participates in the same engine/session lifecycle as the
rest of the API. The session is committed when the handler returns cleanly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.api.deps import get_db_session
from pb_api.cognitive.services import CognitiveCore


async def get_cognitive_core(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CognitiveCore]:
    core = CognitiveCore(session)
    yield core
    await session.commit()


CoreDep = Annotated[CognitiveCore, Depends(get_cognitive_core)]
