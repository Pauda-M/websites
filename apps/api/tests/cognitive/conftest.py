"""Fixtures for Cognitive Core tests.

Each test gets an isolated in-memory SQLite database with the cognitive tables
created, a real ``CognitiveCore`` wired to that session, and a fresh tenant id.
No mocks — services run against real repositories and a real database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import pb_api.cognitive.db.models  # noqa: F401 - registers cognitive tables on Base.metadata
from pb_api.cognitive.config import CognitiveSettings
from pb_api.cognitive.services import CognitiveCore
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
def cognitive_settings() -> CognitiveSettings:
    # Small budgets keep truncation paths exercised in tests.
    return CognitiveSettings(default_token_budget=400, working_memory_ttl_seconds=3600)


@pytest.fixture
def core(session: AsyncSession, cognitive_settings: CognitiveSettings) -> CognitiveCore:
    return CognitiveCore(session, settings=cognitive_settings)


@pytest.fixture
def tenant() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_tenant() -> uuid.UUID:
    return uuid.uuid4()
