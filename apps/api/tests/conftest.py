"""Shared test fixtures.

Tests run against SQLite (aiosqlite) by default so the suite needs no external
services; CI additionally runs it against PostgreSQL by exporting
``TEST_DATABASE_URL``. The app is built through the real factory — no route or
middleware is stubbed out.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pb_api.core.config import Settings
from pb_api.db.base import Base
from pb_api.db.models.user import UserRole
from pb_api.main import create_app


def build_test_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://"),
        "redis_url": None,
        "secret_key": "test-suite-jwt-signing-key-with-plenty-of-entropy",
        "rate_limit_enabled": False,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture
def settings() -> Settings:
    return build_test_settings()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        engine = application.state.engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "correct-horse-battery",
    full_name: str = "Test User",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email or unique_email(), "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    payload: dict[str, object] = response.json()
    return payload


async def login(client: AsyncClient, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    tokens: dict[str, str] = response.json()
    return tokens


async def promote_to_admin(app: FastAPI, email: str) -> None:
    from sqlalchemy import update

    from pb_api.db.models.user import User

    async with app.state.session_factory() as session:
        await session.execute(update(User).where(User.email == email).values(role=UserRole.ADMIN))
        await session.commit()
