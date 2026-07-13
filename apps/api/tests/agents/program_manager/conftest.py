"""Fixtures for Program Manager tests.

Each test gets an isolated in-memory SQLite database with every platform table
created, a real :class:`ProgramManager` (which composes a real Cognitive Core)
wired to that session, and a fresh tenant id. No mocks — services run against
real repositories and a real database, exactly as in production.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import pb_api.agents.program_manager.db.models
import pb_api.cognitive.db.models  # noqa: F401 - registers cognitive tables
from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.config import ProgramManagerSettings
from pb_api.agents.program_manager.domain.common import PMAuthorityLevel
from pb_api.db.base import Base


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
def pm_settings() -> ProgramManagerSettings:
    """Default L1 (act-with-approval) Program Manager."""
    return ProgramManagerSettings(default_authority=PMAuthorityLevel.ACT_WITH_APPROVAL)


@pytest.fixture
def bounded_settings() -> ProgramManagerSettings:
    """An L2 (act-bounded) Program Manager that may take outward actions."""
    return ProgramManagerSettings(default_authority=PMAuthorityLevel.ACT_BOUNDED)


@pytest.fixture
def pm(session: AsyncSession, pm_settings: ProgramManagerSettings) -> ProgramManager:
    return ProgramManager(session, settings=pm_settings)


@pytest.fixture
def bounded_pm(session: AsyncSession, bounded_settings: ProgramManagerSettings) -> ProgramManager:
    return ProgramManager(session, settings=bounded_settings)


@pytest.fixture
def tenant() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_tenant() -> uuid.UUID:
    return uuid.uuid4()
