from __future__ import annotations

from httpx import AsyncClient

from pb_api.platform.modules import (
    OUTREACH_COMPLIANCE_CONTROLS,
    ModuleStatus,
    all_modules,
    get_module,
    outreach_modules,
)

# Every future platform component named in the governance document must have a
# reserved namespace so the architecture stays stable as modules land.
EXPECTED_SLUGS = {
    "identity",
    "observability",
    "marketing-website",
    "crm",
    "client-portal",
    "ai-services",
    "billing",
    "ticketing",
    "knowledge-base",
    "proposal-engine",
    "outbound-sales",
}


def test_registry_covers_every_governed_module() -> None:
    slugs = {module.slug for module in all_modules()}
    assert slugs >= EXPECTED_SLUGS


def test_namespaces_and_slugs_are_unique() -> None:
    modules = all_modules()
    slugs = [m.slug for m in modules]
    assert len(slugs) == len(set(slugs))
    namespaces = [ns for m in modules for ns in m.api_namespace.split(",")]
    assert len(namespaces) == len(set(namespaces))


def test_outreach_modules_carry_all_compliance_controls() -> None:
    outreach = outreach_modules()
    assert outreach, "at least the Outbound Sales Engine must be outreach-gated"
    for module in outreach:
        assert set(module.compliance_controls) == set(OUTREACH_COMPLIANCE_CONTROLS)


def test_non_outreach_modules_have_no_controls() -> None:
    for module in all_modules():
        if module.slug != "outbound-sales":
            assert module.compliance_controls == ()


def test_get_module_lookup() -> None:
    assert get_module("crm") is not None
    assert get_module("does-not-exist") is None


async def test_module_manifest_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/platform/modules")
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == len(all_modules())
    assert body["available"] >= 1
    assert body["planned"] >= 1
    assert body["available"] + body["planned"] == body["total"]

    returned = {module["slug"] for module in body["modules"]}
    assert returned >= EXPECTED_SLUGS

    outbound = next(m for m in body["modules"] if m["slug"] == "outbound-sales")
    assert outbound["status"] == ModuleStatus.PLANNED.value
    assert "human-review-before-first-contact-by-default" in outbound["compliance_controls"]
