"""HTTP-level tests for the Program Manager API, driven through the real app.

These reuse the root ``client`` fixture (a fully-built app over SQLite), so they
exercise routing, dependency wiring, session commit, and metrics end-to-end.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/agents/program-manager/health")
    assert response.status_code == 200
    assert response.json()["employee"] == "program_manager"


async def test_bootstrap_then_run_pauses_for_approval(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    boot = await client.post("/api/v1/agents/program-manager/bootstrap", json={"tenant_id": tenant})
    assert boot.status_code == 201, boot.text

    org = await client.post(
        "/api/v1/agents/program-manager/crm/organizations",
        json={"tenant_id": tenant, "name": "Acme"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    run = await client.post(
        "/api/v1/agents/program-manager/runs",
        json={
            "tenant_id": tenant,
            "trigger": "inbound_message",
            "input_text": "please reply to my question",
            "organization_id": org_id,
        },
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["goal_type"] == "reply_to_customer"
    assert body["awaiting_approval"] is True

    tasks = await client.get(
        f"/api/v1/agents/program-manager/runs/{body['id']}/tasks",
        params={"tenant_id": tenant},
    )
    assert tasks.status_code == 200
    steps = {t["step_key"]: t["status"] for t in tasks.json()}
    assert steps["send"] == "awaiting_approval"


async def test_lead_conversion_flow(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    await client.post("/api/v1/agents/program-manager/bootstrap", json={"tenant_id": tenant})
    org = (
        await client.post(
            "/api/v1/agents/program-manager/crm/organizations",
            json={"tenant_id": tenant, "name": "Beta"},
        )
    ).json()
    lead = (
        await client.post(
            "/api/v1/agents/program-manager/crm/leads",
            json={"tenant_id": tenant, "organization_id": org["id"], "source": "referral"},
        )
    ).json()
    convert = await client.post(
        f"/api/v1/agents/program-manager/crm/leads/{lead['id']}/convert",
        json={"tenant_id": tenant, "name": "Beta Deal", "amount": 5000},
    )
    assert convert.status_code == 201, convert.text
    assert convert.json()["organization_id"] == org["id"]


async def test_convert_without_organization_returns_422(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    await client.post("/api/v1/agents/program-manager/bootstrap", json={"tenant_id": tenant})
    lead = (
        await client.post(
            "/api/v1/agents/program-manager/crm/leads",
            json={"tenant_id": tenant, "source": "website"},
        )
    ).json()
    convert = await client.post(
        f"/api/v1/agents/program-manager/crm/leads/{lead['id']}/convert",
        json={"tenant_id": tenant, "name": "X"},
    )
    assert convert.status_code == 422


async def test_unknown_run_returns_404(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    response = await client.get(
        f"/api/v1/agents/program-manager/runs/{uuid.uuid4()}",
        params={"tenant_id": tenant},
    )
    assert response.status_code == 404


async def test_pm_metrics_exposed_after_a_run(client: AsyncClient) -> None:
    tenant = str(uuid.uuid4())
    await client.post("/api/v1/agents/program-manager/bootstrap", json={"tenant_id": tenant})
    await client.post(
        "/api/v1/agents/program-manager/runs",
        json={"tenant_id": tenant, "input_text": "hi"},
    )
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "pm_runs_total" in metrics.text
