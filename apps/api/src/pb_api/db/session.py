"""Async engine / session wiring.

The engine lives on the FastAPI app state (created in the lifespan) rather
than at module import time, so tests and tooling can build isolated engines
without import-order tricks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pb_api.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": settings.debug, "pool_pre_ping": True}
    # SQLite (used by the test suite and lightweight e2e runs) has no pool tuning.
    if settings.database_url.startswith("postgresql"):
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
    return create_async_engine(settings.database_url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
