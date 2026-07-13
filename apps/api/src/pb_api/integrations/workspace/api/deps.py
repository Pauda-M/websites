"""Workspace API dependencies and app-scoped resource lifecycle.

Provides a per-request :class:`WorkspaceContext` bound to the platform DB session,
and the provider it runs on. The provider is selected by configuration: the
in-memory adapter is an app-scoped singleton (its store persists across requests);
the Microsoft Graph adapter is built per session over an app-scoped HTTP client and
rate limiter. ``init_workspace_state``/``close_workspace_state`` manage those
app-scoped resources from the application lifespan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.api.deps import get_db_session
from pb_api.integrations.workspace.api.metrics import WorkspaceMetrics
from pb_api.integrations.workspace.application.provider_factory import build_graph_provider
from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.config import WorkspaceSettings, get_workspace_settings
from pb_api.integrations.workspace.domain.common import Provider
from pb_api.integrations.workspace.graph.rate_limit import AsyncRateLimiter
from pb_api.integrations.workspace.local import InMemoryWorkspaceProvider
from pb_api.integrations.workspace.ports.providers import WorkspaceProvider


def init_workspace_state(app: FastAPI, settings: WorkspaceSettings | None = None) -> None:
    """Create app-scoped workspace resources at startup."""
    resolved = settings or get_workspace_settings()
    app.state.ws_inmemory_provider = InMemoryWorkspaceProvider()
    app.state.ws_http_client = None
    app.state.ws_rate_limiter = None
    if resolved.provider is Provider.MICROSOFT_GRAPH and resolved.graph_configured:
        app.state.ws_http_client = httpx.AsyncClient(timeout=resolved.http_timeout_seconds)
        app.state.ws_rate_limiter = AsyncRateLimiter(resolved.rate_limit_per_second)


async def close_workspace_state(app: FastAPI) -> None:
    """Release app-scoped workspace resources at shutdown."""
    client = getattr(app.state, "ws_http_client", None)
    if client is not None:
        await client.aclose()


def _provider_for(request: Request, session: AsyncSession) -> WorkspaceProvider:
    settings = get_workspace_settings()
    state = request.app.state
    if (
        settings.provider is Provider.MICROSOFT_GRAPH
        and settings.graph_configured
        and getattr(state, "ws_http_client", None) is not None
    ):
        return build_graph_provider(
            session,
            settings,
            http_client=state.ws_http_client,
            rate_limiter=state.ws_rate_limiter,
        )
    provider = getattr(state, "ws_inmemory_provider", None)
    if not isinstance(provider, InMemoryWorkspaceProvider):
        provider = InMemoryWorkspaceProvider()
        state.ws_inmemory_provider = provider
    return provider


async def get_workspace_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[WorkspaceContext]:
    context = WorkspaceContext(session, provider=_provider_for(request, session))
    yield context
    await session.commit()


def get_workspace_metrics(request: Request) -> WorkspaceMetrics:
    existing = getattr(request.app.state, "ws_metrics", None)
    if isinstance(existing, WorkspaceMetrics):
        return existing
    metrics = WorkspaceMetrics(request.app.state.metrics.registry)
    request.app.state.ws_metrics = metrics
    return metrics


WsDep = Annotated[WorkspaceContext, Depends(get_workspace_context)]
WsMetricsDep = Annotated[WorkspaceMetrics, Depends(get_workspace_metrics)]
