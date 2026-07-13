"""Fixtures for workspace-integration tests.

Each test gets an isolated in-memory SQLite database with every platform table
created, a real :class:`WorkspaceContext` wired to an in-memory provider whose
:class:`InMemoryStore` the test can seed (the simulated external Microsoft 365),
and a bootstrapped connection. No mocks — services run against real repositories,
a real Cognitive Core, and the fully-functional in-memory adapter.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import pb_api.agents.program_manager.db.models
import pb_api.cognitive.db.models
import pb_api.integrations.workspace.db.models  # noqa: F401
from pb_api.db.base import Base
from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.local import InMemoryStore, InMemoryWorkspaceProvider


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def provider(store: InMemoryStore) -> InMemoryWorkspaceProvider:
    return InMemoryWorkspaceProvider(store)


@pytest.fixture
def ctx(session: AsyncSession, provider: InMemoryWorkspaceProvider) -> WorkspaceContext:
    return WorkspaceContext(session, provider=provider)


@pytest.fixture
def tenant() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_tenant() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def connection(ctx: WorkspaceContext, tenant: uuid.UUID) -> WorkspaceConnection:
    return await ctx.bootstrap_connection(
        tenant, display_name="Support Mailbox", mailbox="support@acme.test"
    )
