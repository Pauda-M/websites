# ADR-0005: Edge and deployment

## Status

Accepted — 2026-07-13

## Context

The platform must run as a coherent stack (edge proxy, web, API, database,
cache, migrations) that is identical across local, staging, and production —
differing only by configuration — and that a small team (and autonomous agents)
can deploy to a single Docker host today without adopting a cluster
orchestrator. TLS, HTTP→HTTPS redirection, routing by hostname, and keeping the
internal databases off the public internet are all required from day one.

## Decision

**Edge: Traefik v3.** Traefik (`traefik:v3.3` in `docker-compose.yml`) is the
only ingress. It terminates TLS, redirects the `web` entrypoint (`:80`) to
`websecure` (`:443`), routes by hostname (web on the apex, API on the `api.`
subdomain), and applies edge middleware. Databases sit on an internal Docker
network with no published ports in production.

Traefik's **static configuration is passed as CLI flags, not a `--configfile`**.
This is deliberate: mixing `--configfile` with other static flags makes Traefik
ignore the flags, and Compose _replaces_ (does not merge) the `command` list in
an overlay. Because the base config is flags, `docker-compose.prod.yml` restates
the full base `command` and appends the ACME resolver flags — so the Let's
Encrypt `--certificatesresolvers.letsencrypt.acme.email=${PB_ACME_EMAIL}`
actually takes effect. Dynamic configuration stays a file provider
(`infra/traefik/dynamic/security.yml`).

**Stack: Docker Compose.** `docker-compose.yml` runs the full stack —
`postgres:17-alpine`, `redis:7-alpine`, a **one-shot `migrations` service**
(`alembic upgrade head`, `restart: "no"`), the `api`, the `web`, and Traefik.
Startup ordering is enforced in the compose graph: PostgreSQL/Redis become
healthy → `migrations` runs and must exit 0
(`condition: service_completed_successfully`) → `api` starts → `web` starts. App
containers never mutate the schema at import time.

**Production overlay.** `docker-compose.prod.yml` layers hardening:
`PB_ENVIRONMENT=production`, the ACME certificate resolver, and
`ports: !override []` on postgres and redis (the `!override` tag clears the
merged list; a plain `ports: []` would merge and leave the host binding in
place).

**Metrics are internal-only.** A higher-priority Traefik router
(`api-metrics`, `priority=100`) matches `PathPrefix(/metrics)` and applies the
`internal-only@file` middleware — an `ipAllowList` restricted to loopback and
RFC1918 ranges (`infra/traefik/dynamic/security.yml`) — so `/metrics` is never
reachable from the public internet. Prometheus is expected to scrape the API
container directly over the internal network.

## Alternatives Considered

- **nginx as the edge.** Battle-tested and fast, but static config and manual
  certificate automation (certbot) mean more moving parts; Traefik's Docker
  provider derives routing from container labels and automates ACME. Rejected
  for the operational overhead.
- **Kubernetes now.** Real rolling deploys, autoscaling, and self-healing, but
  substantial operational complexity for a single-host, small-team phase.
  Rejected as premature; Compose covers the current need and the stateless API
  keeps a later migration open.
- **A cloud load balancer + managed certificates.** Offloads TLS and DNS, but
  couples the platform to one cloud and does not give the identical
  local/prod stack Compose provides. Rejected now; managed PostgreSQL and an
  external LB remain drop-in options later.

## Consequences

- One command deploys the whole stack, and the same images run everywhere:
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
- Migrations run automatically and gate the API: a failed migration stops the
  rollout before the new API serves traffic.
- The flags-not-configfile choice is load-bearing and non-obvious — the base
  `command` must be kept in sync between `docker-compose.yml` and the prod
  overlay whenever a static flag changes. This is documented in the compose
  files themselves.
- `/metrics` exposure depends on the edge middleware plus the API's own exempt
  handling; both layers must stay in place.
- Losing the `letsencrypt` volume is harmless (certificates re-issue, subject to
  Let's Encrypt rate limits); losing `postgres-data` is not (see backups in
  `docs/OPERATIONS.md`).

## Future Considerations

- Managed PostgreSQL (swap `PB_API_DATABASE_URL`, drop the bundled service) when
  durability or load demands it.
- Kubernetes or a cloud runtime if multi-host scaling, zero-downtime rollouts,
  or self-healing become requirements — the stateless API is the enabler.
- A Docker socket proxy in front of Traefik's read-only socket mount to reduce
  the blast radius of the mounted `docker.sock` (tracked in
  `docs/SECURITY.md`).
