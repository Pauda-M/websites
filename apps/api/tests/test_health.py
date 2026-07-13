from __future__ import annotations

from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "pb-api"
    assert body["environment"] == "test"
    assert body["version"]


async def test_readiness_reports_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    # Redis is not configured in the default test settings.
    assert body["checks"]["redis"] == "skipped"


async def test_request_id_header_present(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.headers.get("X-Request-ID")


async def test_inbound_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": "edge-trace-123"})
    assert response.headers["X-Request-ID"] == "edge-trace-123"
