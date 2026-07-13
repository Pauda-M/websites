"""Program Manager API dependencies.

Provides a per-request :class:`ProgramManager` bound to the platform's DB session
(committed when the handler returns cleanly, mirroring the Cognitive Core), and a
lazily-constructed :class:`ProgramManagerMetrics` registered on the application's
metrics registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.agents.program_manager.api.metrics import ProgramManagerMetrics
from pb_api.agents.program_manager.application import ProgramManager
from pb_api.api.deps import get_db_session


async def get_program_manager(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ProgramManager]:
    manager = ProgramManager(session)
    yield manager
    await session.commit()


def get_pm_metrics(request: Request) -> ProgramManagerMetrics:
    """Return the app-scoped PM metrics, creating them once per application.

    Registered on the application's existing CollectorRegistry so PM metrics are
    exported by the same ``/metrics`` endpoint and are isolated per app instance.
    """
    existing = getattr(request.app.state, "pm_metrics", None)
    if isinstance(existing, ProgramManagerMetrics):
        return existing
    metrics = ProgramManagerMetrics(request.app.state.metrics.registry)
    request.app.state.pm_metrics = metrics
    return metrics


PMDep = Annotated[ProgramManager, Depends(get_program_manager)]
PMMetricsDep = Annotated[ProgramManagerMetrics, Depends(get_pm_metrics)]
