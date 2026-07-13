"""HTTP-level tests for the workspace API, driven through the real app.

These reuse the root ``client`` fixture (a fully-built app over SQLite with the
in-memory workspace provider wired at startup), so they exercise routing,
dependency injection, session commit, and metrics end-to-end.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _connect(client: AsyncClient, tenant: str) -> str:
    response = await client.post(
        "/api/v1/integrations/workspace/connections",
        json={"tenant_id": tenant, "display_name": "Support", "mailbox": "support@acme.test"},
    )
    assert response.status_code == 201, response.text
    connection_id: str = response.json()["id"]
    return connection_id


async def test_live_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/integrations/workspace/live")
    assert response.status_code == 200
    assert response.json()["integration"] == "workspace"


async def test_connect_and_health(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    await _connect(client, tenant)
    listed = await client.get(
        "/api/v1/integrations/workspace/connections", params={"tenant_id": tenant}
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    health = await client.get(
        "/api/v1/integrations/workspace/connections/health", params={"tenant_id": tenant}
    )
    assert health.status_code == 200
    assert health.json()["connections"] == 1


async def test_sync_run_and_status(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    connection_id = await _connect(client, tenant)
    run = await client.post(
        "/api/v1/integrations/workspace/sync/run",
        json={"tenant_id": tenant, "connection_id": connection_id},
    )
    assert run.status_code == 200, run.text
    jobs = run.json()["jobs"]
    assert len(jobs) == 5
    assert all(job["status"] == "succeeded" for job in jobs)
    status = await client.get(
        "/api/v1/integrations/workspace/sync/status", params={"tenant_id": tenant}
    )
    assert status.status_code == 200
    assert len(status.json()) >= 5


async def test_approval_policy_crud_and_pending(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    await _connect(client, tenant)  # bootstrap seeds default policies
    policies = await client.get(
        "/api/v1/integrations/workspace/approvals/policies", params={"tenant_id": tenant}
    )
    assert policies.status_code == 200
    seeded = len(policies.json())
    created = await client.post(
        "/api/v1/integrations/workspace/approvals/policies",
        json={
            "tenant_id": tenant,
            "name": "auto-approve-replies",
            "decision": "approve_automatically",
            "communication_type": "mail_reply",
            "priority": 90,
        },
    )
    assert created.status_code == 201, created.text
    policies2 = await client.get(
        "/api/v1/integrations/workspace/approvals/policies", params={"tenant_id": tenant}
    )
    assert len(policies2.json()) == seeded + 1
    pending = await client.get(
        "/api/v1/integrations/workspace/approvals/pending", params={"tenant_id": tenant}
    )
    assert pending.status_code == 200
    assert pending.json() == []


async def test_search_and_mail_empty(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    connection_id = await _connect(client, tenant)
    search = await client.get(
        "/api/v1/integrations/workspace/search",
        params={"tenant_id": tenant, "query": "anything"},
    )
    assert search.status_code == 200
    assert search.json() == []
    mail = await client.get(
        "/api/v1/integrations/workspace/mail",
        params={"tenant_id": tenant, "connection_id": connection_id},
    )
    assert mail.status_code == 200
    assert mail.json() == []
