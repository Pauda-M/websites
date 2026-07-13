# ADR-0008: Modular namespace reservation

## Status

Accepted — 2026-07-13

## Context

PB Platform is a modular monolith today and a set of independently deployable
services tomorrow. It is designed to host a known set of product modules — CRM,
Client Portal, AI Services, Billing, Ticketing, Knowledge Base, Proposal Engine,
Marketing Website, and an Outbound Sales Engine — most of which are not built
yet. The team needs the API's URL layout to be stable and discoverable from day
one so modules can land without renaming existing routes or colliding on
prefixes. Governance forbids placeholder logic and prototypes, so the reservation
must not take the form of empty stub packages sitting around waiting for code.

## Decision

We maintain an authoritative, tested **platform module registry** in
`apps/api/src/pb_api/platform/modules.py`. Each `PlatformModule` is a frozen
dataclass declaring a `slug`, `name`, `category` (`core` | `product`), `status`
(`available` | `planned`), a reserved `api_namespace` under `/api/v1`, a
`description`, and optional `compliance_controls`. The registry reserves stable
namespaces for every governed module:

- **Available:** Identity & Access (`/api/v1/auth`, `/api/v1/users`),
  Observability (`/api/v1/health`, `/metrics`), Marketing Website
  (`/api/v1/marketing`).
- **Planned:** CRM (`/api/v1/crm`), Client Portal (`/api/v1/portal`), AI Services
  (`/api/v1/ai`), Billing (`/api/v1/billing`), Ticketing (`/api/v1/ticketing`),
  Knowledge Base (`/api/v1/kb`), Proposal Engine (`/api/v1/proposals`), Outbound
  Sales Engine (`/api/v1/outbound`).

The manifest is served at **`GET /api/v1/platform/modules`**
(`api/routes/platform.py`), returning totals plus each module's status,
namespace, and controls — so internal admin/monitoring surfaces and anyone
reading the OpenAPI spec can see what exists, what is reserved, and what
outreach controls apply. Modules are loosely coupled and intended to become
independently deployable; the registry commits the platform to a layout without
coupling the modules to each other.

**Reserving via a tested registry — not empty stub packages — is the core of the
decision.** Stub packages would be placeholder logic (which governance
prohibits) and would rot; a declarative registry carries no runtime behaviour to
rot, and tests (`apps/api/tests/test_platform.py`) assert that every governed
module has a reserved slug, that slugs and namespaces are unique, and that the
manifest endpoint reports them. Drift between the intended architecture and the
running system is therefore caught automatically.

## Alternatives Considered

- **Empty stub apps/packages per future module.** Makes the namespaces
  physically present, but is exactly the placeholder scaffolding governance
  forbids: dead code that drifts, adds build/lint surface, and implies
  functionality that does not exist. Rejected.
- **No reservation at all — add namespaces when each module is built.**
  Zero upfront work, but invites prefix collisions, inconsistent naming, and
  ad-hoc URL layouts decided module by module, with nothing discoverable in the
  meantime. Rejected.
- **A separate registry service.** Over-engineered for a static manifest: it
  would add a deployable and a network hop to serve data that is a constant.
  Rejected; an in-process registry with an endpoint is sufficient.

## Consequences

- The API's URL layout is stable, documented, and discoverable via one endpoint
  and the OpenAPI spec, before most modules exist.
- New modules slot into their reserved namespace without touching existing
  routes; adding one is a registry entry plus the actual implementation.
- The registry is a single source of truth that tests hold to the governance
  document, so a missing or renamed module fails the test suite.
- The manifest carries no behaviour, so it stays cheap and cannot become stale
  placeholder logic.
- The registry is the natural place ADR-0009 attaches outreach compliance
  controls to outreach-capable modules.

## Future Considerations

- As `planned` modules are implemented and mounted, flip their `status` to
  `available` and add their routers; the namespace is already committed.
- Per-module metadata could grow (owning team, docs link, deployment target) as
  modules become independently deployable services.
- If modules split into separate services, the registry can become the source
  for a gateway/routing manifest rather than in-process route mounting.
