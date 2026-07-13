"""Platform module registry.

PB Platform is a modular monolith today and a set of independently deployable
services tomorrow. This registry is the authoritative manifest of the product
modules the platform is designed to host: their reserved API namespace, their
lifecycle status, and — for modules that contact customers or prospects — the
compliance controls a future implementation is required to ship with.

Reserving namespaces here (rather than leaving empty stub packages around)
keeps the codebase free of placeholder logic while still committing the
platform to a stable, discoverable module layout. The manifest is served by
``GET /api/v1/platform/modules`` and is covered by tests, so drift between the
intended architecture and the running system is caught automatically.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ModuleStatus(enum.StrEnum):
    """Lifecycle of a platform module."""

    AVAILABLE = "available"  # implemented and serving traffic
    PLANNED = "planned"  # namespace reserved, not yet implemented


class ModuleCategory(enum.StrEnum):
    CORE = "core"  # cross-cutting platform capability
    PRODUCT = "product"  # customer-facing product surface


@dataclass(frozen=True, slots=True)
class PlatformModule:
    """Declarative description of a platform module.

    ``api_namespace`` is the URL prefix reserved under ``/api/v1`` for this
    module. ``compliance_controls`` lists mandatory controls a future
    implementation must satisfy before the module may contact people — the
    governance requirement for outreach features is encoded here so it cannot
    be forgotten.
    """

    slug: str
    name: str
    category: ModuleCategory
    status: ModuleStatus
    api_namespace: str
    description: str
    compliance_controls: tuple[str, ...] = field(default_factory=tuple)


# Controls mandated by AI_DEPLOY_AUTHORIZATION.md for any module that contacts
# customers or prospects. Referenced by the outreach-capable modules below.
OUTREACH_COMPLIANCE_CONTROLS: tuple[str, ...] = (
    "maintain-suppression-and-opt-out-lists",
    "prevent-duplicate-outreach",
    "log-outreach-history",
    "configurable-compliance-rules",
    "human-review-before-first-contact-by-default",
    "no-deceptive-or-misleading-messaging",
)


# The registry. Order is display order. Slugs and namespaces are stable API.
MODULE_REGISTRY: tuple[PlatformModule, ...] = (
    PlatformModule(
        slug="identity",
        name="Identity & Access",
        category=ModuleCategory.CORE,
        status=ModuleStatus.AVAILABLE,
        api_namespace="/api/v1/auth,/api/v1/users",
        description=(
            "Authentication, JWT session issuance, and role-based access control. "
            "The foundation every other module builds on."
        ),
    ),
    PlatformModule(
        slug="observability",
        name="Observability",
        category=ModuleCategory.CORE,
        status=ModuleStatus.AVAILABLE,
        api_namespace="/api/v1/health,/metrics",
        description="Health and readiness probes, Prometheus metrics, and structured logging.",
    ),
    PlatformModule(
        slug="marketing-website",
        name="Marketing Website",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.AVAILABLE,
        api_namespace="/api/v1/marketing",
        description=(
            "Public consulting site and lead capture. The landing experience is live in "
            "apps/web; server-side content APIs are reserved under this namespace."
        ),
    ),
    PlatformModule(
        slug="crm",
        name="CRM",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/crm",
        description="Contacts, companies, deals, and the pipeline that powers PB Solutions sales.",
    ),
    PlatformModule(
        slug="client-portal",
        name="Client Portal",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/portal",
        description="Authenticated client workspace: projects, deliverables, documents, messaging.",
    ),
    PlatformModule(
        slug="ai-services",
        name="AI Services",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/ai",
        description="AI agents and assistants offered as a product surface and internal tooling.",
    ),
    PlatformModule(
        slug="billing",
        name="Billing & Invoicing",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/billing",
        description="Invoicing, payments, subscriptions, and revenue reporting.",
    ),
    PlatformModule(
        slug="ticketing",
        name="Ticketing",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/ticketing",
        description="Support tickets, SLAs, and the agent inbox.",
    ),
    PlatformModule(
        slug="knowledge-base",
        name="Knowledge Base",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/kb",
        description="Public and internal articles, categories, and search.",
    ),
    PlatformModule(
        slug="proposal-engine",
        name="Proposal Engine",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/proposals",
        description="Proposal generation, templating, e-signature, and acceptance tracking.",
    ),
    PlatformModule(
        slug="outbound-sales",
        name="Outbound Sales Engine",
        category=ModuleCategory.PRODUCT,
        status=ModuleStatus.PLANNED,
        api_namespace="/api/v1/outbound",
        description=(
            "Prospecting and outbound outreach. Contacts people, so it is gated by the "
            "outreach compliance controls and must not ship without them."
        ),
        compliance_controls=OUTREACH_COMPLIANCE_CONTROLS,
    ),
)


def all_modules() -> tuple[PlatformModule, ...]:
    return MODULE_REGISTRY


def get_module(slug: str) -> PlatformModule | None:
    return next((module for module in MODULE_REGISTRY if module.slug == slug), None)


def outreach_modules() -> tuple[PlatformModule, ...]:
    """Modules that contact people and therefore carry compliance controls."""
    return tuple(module for module in MODULE_REGISTRY if module.compliance_controls)
