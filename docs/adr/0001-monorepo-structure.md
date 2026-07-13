# ADR-0001: Monorepo structure

## Status

Accepted — 2026-07-13

## Context

PB Platform is the single operating system for PB Solutions. It starts as a
public consulting website plus an API and is designed to grow into a suite of
product surfaces (CRM, client portal, AI services, ticketing, knowledge base,
proposals, billing, outbound sales). These surfaces will be built in different
languages (Python for services, TypeScript for the web) but must share
contracts, tooling, and a single quality bar.

The work is largely carried out by autonomous engineering agents under
[`AI_DEPLOY_AUTHORIZATION.md`](../../AI_DEPLOY_AUTHORIZATION.md), which requires
consistent conventions, a single validation loop, and no placeholder scaffolding.
That pushes toward one repository where a change can be reasoned about, tested,
and validated atomically, rather than many repositories that drift.

## Decision

We keep everything in one monorepo, managed by **pnpm** (JS/TS workspaces) and
**uv** (Python), split into top-level directories by role:

- `apps/` — independently deployable applications, each with its own Dockerfile
  and health/metrics surface (`apps/api`, `apps/web`).
- `packages/` — shared JS/TS libraries (`packages/api-client`,
  `packages/tsconfig`).
- `shared/` — cross-language contracts (`shared/openapi/openapi.json`, exported
  from the live API via `make openapi`).
- `infra/` — infrastructure configuration (`infra/traefik/`).
- `docs/` — architecture, guides, and these ADRs.
- `scripts/` — operational scripts (e.g. `scripts/export_openapi.py`).
- `tests/` — cross-service black-box suites (`tests/e2e`, Playwright).

The boundary rules, enforced by convention and reflected in
`docs/ARCHITECTURE.md`:

1. **Apps never import from other apps.** Cross-app communication is over HTTP
   contracts (the OpenAPI spec in `shared/openapi/`), never through shared code.
   `apps/web` reaches `apps/api` only through the typed `@pb/api-client`
   package.
2. **Each app is independently deployable** — its own Dockerfile, its own
   dependency lockfile scope, its own health endpoints and metrics.
3. **Shared code is promoted deliberately**: the second consumer is what moves
   code into `packages/` (TS) or a future `libs/` (Python).
4. **Contracts are generated, not hand-maintained**: `make openapi` exports the
   spec from FastAPI and `@pb/api-client` mirrors it under test.

The `Makefile` is the canonical entry point for every workflow, and CI
(`.github/workflows/ci.yml`) runs the same targets, so local and CI behaviour
cannot diverge.

## Alternatives Considered

- **Polyrepo (one repository per app/library).** Gives each service a hard
  boundary and independent history, but makes atomic cross-cutting changes
  (a contract change touching API + client + web) span several pull requests,
  duplicates tooling and CI, and invites version drift between the API and its
  client. Rejected: the coordination cost outweighs the isolation benefit at
  this stage, and the monorepo already enforces app independence by convention.
- **A single application (no `apps/` split).** Fewer moving parts early on, but
  it fuses the Python service and the Next.js site into one deploy unit, blocks
  independent scaling, and forces one runtime/toolchain to host both. Rejected:
  the platform explicitly needs multiple independently deployable surfaces.

## Consequences

- One clone, one install (`make setup`), one validation loop
  (`make lint typecheck test`, plus `make test-e2e`) covers the whole system.
- Cross-cutting changes land atomically and are validated together; the e2e
  suite boots the real API and web build so a broken contract fails CI.
- The `apps/` boundary must be defended in review — there is no build-time
  barrier stopping one app from importing another, so the discipline is social
  plus the e2e/contract tests that would break if boundaries were crossed.
- Two package managers (pnpm and uv) coexist; contributors need both toolchains
  installed, and the `.prettierignore` deliberately excludes `apps/api` so the
  Python tree is formatted by Black/Ruff rather than Prettier.
- The legacy `compound-calculator/` page predates the platform and is
  intentionally left unmanaged (excluded from Prettier), documenting that not
  every directory is under the platform's conventions yet.

## Future Considerations

- A `libs/` tree for shared Python code once a second Python service exists
  (mirroring how `packages/` serves TypeScript).
- Additional deployable apps (`apps/portal`, `apps/ai`) as product modules land;
  the layout and boundary rules already anticipate them.
- If the repository grows large enough that full-repo CI becomes slow, introduce
  path-based build filtering rather than splitting into polyrepos.
