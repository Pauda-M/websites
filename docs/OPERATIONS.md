# PB Platform — Operations

Day-2 operations for the running stack: deploying, checking health, reading
telemetry, migrating, provisioning, backing up, scaling, and tuning. This
complements `docs/DEPLOYMENT.md` (first-time setup) and `docs/TROUBLESHOOTING.md`
(when something is wrong). All commands run from the repository root unless
noted. Production commands assume the prod overlay; drop it for a local stack.

## Deploy and redeploy

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps            # api/web/traefik Up (healthy); migrations Exited (0)
```

Startup ordering is enforced by the compose graph: PostgreSQL/Redis become
healthy → the one-shot `migrations` service runs `alembic upgrade head` and must
exit 0 → `api` starts (its healthcheck gates Traefik) → `web` starts. A failed
migration halts the rollout before the new API serves traffic. Images are
self-contained, so a redeploy is just a rebuild — no host build artifacts are
read at runtime.

Rollback is roll-forward by preference: check out the previous tag/commit and
`up -d --build` again. Down-migrations exist (`alembic downgrade -1`) but take a
backup before any risky release (see Backups).

## Health and readiness

```bash
curl -fsS https://api.$PB_DOMAIN/api/v1/health/live     # process is serving
curl -fsS https://api.$PB_DOMAIN/api/v1/health/ready    # dependencies checked
```

- **Liveness** (`/api/v1/health/live`) never touches dependencies — it only
  reports that the process is up (with service, version, environment). Use it for
  "should the orchestrator restart this container".
- **Readiness** (`/api/v1/health/ready`) checks PostgreSQL (`SELECT 1`) and, when
  configured, Redis (`PING`). It returns **200** with
  `{"status": "ok", "checks": {...}}` when all are healthy, and **503** with
  `{"status": "degraded", ...}` when any check is `error`. The `checks` object
  names each dependency (`database`, `redis`) with `ok`, `error`, or `skipped`
  (Redis when unconfigured).
- **"Degraded" means**: the process is alive (liveness stays green) but at least
  one dependency is unreachable, so an orchestrator/load balancer should stop
  routing new traffic to this instance until it recovers. The `/status` page on
  the web app renders the same readiness data server-side.

## Reading logs

Every service logs **one JSON object per line** (structlog for the API, JSON log

- access log for Traefik). Point your collector at the Docker log driver.

```bash
docker compose logs -f --tail=100 api web traefik
```

Each API request produces one access line with `event: "request"` carrying
`method`, `path`, `status`, `duration_ms`, and `client`, plus a `request_id`.
That **`request_id`** is bound into every log line emitted while handling the
request (and echoed to the client on the `X-Request-ID` response header), so to
trace one request end to end, filter logs by its `request_id`. An inbound
`X-Request-ID` from the edge is honoured, so IDs can be correlated across
services. Set verbosity with `PB_API_LOG_LEVEL` (default `INFO`);
`PB_API_LOG_JSON` can force JSON or console rendering.

## Metrics

The API exposes Prometheus metrics at **`/metrics`**, served over the internal
network only (Traefik restricts it to internal IPs; it is not routed publicly).
Scrape the api container directly on port 8000. The runtime image is a slim
Python image (no `curl`/`wget`), so fetch with Python — the same approach the
container's own healthcheck uses:

```bash
docker compose exec api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())" | head
```

Series exposed: `http_requests_total` (labels `method`, `path`, `status`),
`http_request_duration_seconds` (histogram, labels `method`, `path`), and
`http_requests_in_flight` (gauge). The `path` label is the matched route
template (e.g. `/api/v1/users/{user_id}`), not the raw URL, so cardinality stays
bounded. Point a Prometheus scrape job at each api replica over the internal
network.

## Migrations

Schema changes are Alembic migrations under `apps/api/alembic/`. In the compose
stack they run automatically via the one-shot `migrations` service on every
`up`. To run them manually:

```bash
docker compose run --rm migrations                       # alembic upgrade head
```

For a local (non-Docker) database, the Makefile target applies them against your
configured `PB_API_DATABASE_URL`:

```bash
make migrate                                             # alembic upgrade head
```

Roll a single migration back with
`cd apps/api && uv run alembic downgrade -1` (prefer roll-forward fixes in
production).

## Creating admin/staff users

Privileged accounts are never created through the public API — use the CLI. In
the compose stack, run it in a one-shot container that shares the API image and
database config:

```bash
docker compose run --rm migrations \
  python -m pb_api.cli create-admin --email admin@example.com --full-name "Ada Admin"
```

Locally:

```bash
cd apps/api && uv run python -m pb_api.cli create-admin \
  --email admin@example.com --full-name "Ada Admin"
```

Add `--role staff` for a staff account (default is `admin`). Omit `--password` to
have a strong one generated and printed **once** — capture it immediately.

## Database backup and restore

PostgreSQL data lives in the `postgres-data` volume. Back it up with `pg_dump`
and ship the dumps off-host (schedule via cron/systemd timer):

```bash
docker compose exec postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup-$(date +%F).sql.gz
```

Restore into a running database (the inverse — pipe the dump back through
`psql`):

```bash
gunzip -c backup-2026-07-13.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Redis holds only rate-limit counters in phase 1 and needs no backup.

## Scaling the API

The API is stateless (JWT auth, shared state in PostgreSQL/Redis), so it scales
horizontally and Traefik load-balances the replicas:

```bash
docker compose up -d --scale api=3
```

The Redis rate-limiter stays correct across replicas because counting is atomic
in Redis — this is why configuring `PB_API_REDIS_URL` matters once you run more
than one instance. Move PostgreSQL to managed hosting (swap
`PB_API_DATABASE_URL`, drop the bundled service) when load or durability demands
it.

## Certificate renewal

In production, Traefik obtains and **renews certificates automatically** via the
Let's Encrypt ACME resolver, storing material in the `letsencrypt` Docker volume
(`/letsencrypt/acme.json`). No manual renewal is needed. Losing the volume is
harmless — certificates are re-issued on next start, subject to Let's Encrypt
rate limits. Ensure ports 80 and 443 stay reachable (the HTTP-01 challenge uses
port 80) and that `PB_ACME_EMAIL` is set (the prod overlay requires it).

## Tuning the rate limiter

The limiter is configured entirely by environment (`middleware/rate_limit.py`):

- `PB_API_RATE_LIMIT_PER_MINUTE` (default `120`) — per-IP fixed-window budget.
- `PB_API_RATE_LIMIT_ENABLED` (default `true`) — master switch.
- `PB_API_TRUST_PROXY_HEADERS` (compose sets `true`) — required behind Traefik so
  the real client IP (from `X-Forwarded-For`) is used rather than the proxy's.

Health and metrics paths are always exempt. Over-limit responses are HTTP 429
with a `Retry-After` header telling the client how long to wait. Raise the budget
if legitimate clients hit 429s; if Redis is unreachable the limiter fails open
(requests are allowed) and logs `rate_limiter_unavailable`.
