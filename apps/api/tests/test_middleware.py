from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pb_api.main import create_app
from tests.conftest import build_test_settings


async def test_security_headers_present(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    # HSTS only makes sense behind TLS; it must NOT be set outside production.
    assert "Strict-Transport-Security" not in response.headers


async def test_hsts_emitted_when_enabled() -> None:
    # Production wires SecureHeadersMiddleware(enable_hsts=True); assert the
    # header the production path depends on is actually emitted.
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from pb_api.middleware.secure_headers import SecureHeadersMiddleware

    async def ok(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(SecureHeadersMiddleware, enable_hsts=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        response = await http_client.get("/")
    hsts = response.headers["Strict-Transport-Security"]
    assert "max-age=63072000" in hsts
    assert "includeSubDomains" in hsts


async def test_cors_preflight_allows_configured_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


async def test_cors_preflight_rejects_unknown_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "Access-Control-Allow-Origin" not in response.headers


async def test_metrics_endpoint_exposes_prometheus_counters(client: AsyncClient) -> None:
    await client.get("/api/v1/health/live")
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text
    assert "/api/v1/health/live" in text


@pytest.fixture
async def rate_limited_client() -> AsyncIterator[AsyncClient]:
    settings = build_test_settings(rate_limit_enabled=True, rate_limit_per_minute=3)
    application: FastAPI = create_app(settings)
    # Pin the limiter clock so a real 60s window boundary can never roll over
    # mid-test — the assertions below become deterministic.
    application.state.rate_limit_backend._time_fn = lambda: 1000.0
    async with application.router.lifespan_context(application):
        engine = application.state.engine
        from pb_api.db.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
            yield http_client


async def test_rate_limit_enforced(rate_limited_client: AsyncClient) -> None:
    # Limit is 3/minute; the 4th request must be rejected.
    for _ in range(3):
        response = await rate_limited_client.post(
            "/api/v1/auth/login", json={"email": "rl@example.com", "password": "x-y-z-1-2-3"}
        )
        assert response.status_code == 401

    blocked = await rate_limited_client.post(
        "/api/v1/auth/login", json={"email": "rl@example.com", "password": "x-y-z-1-2-3"}
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_rate_limit_exempts_health(rate_limited_client: AsyncClient) -> None:
    for _ in range(10):
        response = await rate_limited_client.get("/api/v1/health/live")
        assert response.status_code == 200
