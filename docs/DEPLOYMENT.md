# PB Platform — Deployment Guide

How to run the stack in production on a Docker host. The same images and
compose files run everywhere; production differs only by overlay and
environment.

## 1. Overview

Two compose files:

- `docker-compose.yml` — the full stack: Traefik, api, web, migrations
  (one-shot), PostgreSQL, Redis. Suitable for local/dev as-is.
- `docker-compose.prod.yml` — production overlay: Let's Encrypt (ACME)
  certificates, `PB_ENVIRONMENT=production`, no database ports published on
  the host.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Startup ordering is enforced in the compose graph: PostgreSQL/Redis become
healthy → `migrations` runs `alembic upgrade head` and must exit 0 → `api`
starts (its own healthcheck gates Traefik-visible readiness) → `web` starts.

## 2. Prerequisites

- A Linux host with Docker Engine 24+ and the compose plugin.
- DNS: `A` records for `pb-solutions.today` and `api.pb-solutions.today`
  pointing at the host (Traefik routes web on the apex and API on the `api.`
  subdomain).
- Ports 80 and 443 reachable from the internet (ACME HTTP-01 challenge).

## 3. Configuration

```bash
cp .env.example .env
```

Set at minimum:

| Variable              | Production value                                      |
| --------------------- | ----------------------------------------------------- |
| `PB_ENVIRONMENT`      | `production` (also forced by the prod overlay)        |
| `PB_DOMAIN`           | your apex domain, e.g. `pb-solutions.today`           |
| `PB_ACME_EMAIL`       | ops email for Let's Encrypt expiry notices            |
| `POSTGRES_PASSWORD`   | long random string                                    |
| `PB_API_SECRET_KEY`   | ≥32 chars of real entropy (`openssl rand -base64 48`) |
| `PB_API_CORS_ORIGINS` | `["https://pb-solutions.today"]`                      |
| `NEXT_PUBLIC_API_URL` | `https://api.pb-solutions.today`                      |

The API **refuses to boot** in production with a placeholder secret, wildcard
CORS, or a non-PostgreSQL database — misconfiguration fails loudly at start,
not quietly at runtime.

### Secrets policy

`.env` on the host is the phase-1 mechanism: keep it `chmod 600`, owned by
the deploy user, and never committed. When moving to a secret store (Vault,
SSM, Docker secrets), inject the same variables into the containers — the
application only ever reads the environment, so nothing changes in code.

## 4. Deploying

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps        # everything Up/healthy, migrations Exited (0)
```

Schema migrations run automatically via the `migrations` service before the
new API starts. Images are self-contained; no build artifacts are read from
the host at runtime.

### Verifying a deploy

```bash
curl -fsS https://api.$PB_DOMAIN/api/v1/health/live
curl -fsS https://api.$PB_DOMAIN/api/v1/health/ready   # database + redis "ok"
curl -fsSI https://$PB_DOMAIN | head -5
```

`/status` on the web app shows the same readiness data rendered server-side.

## 5. Operations

| Task              | Command                                                                                                                                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Tail logs         | `docker compose logs -f --tail=100 api web traefik`                                                                                                                                                          |
| Restart a service | `docker compose restart api`                                                                                                                                                                                 |
| Manual migration  | `docker compose run --rm migrations`                                                                                                                                                                         |
| Create admin user | `docker compose run --rm migrations python -m pb_api.cli create-admin --email ... --full-name ...`                                                                                                           |
| Metrics           | `GET /metrics` on the api container over the internal network. At the edge a dedicated Traefik router restricts `/metrics` to private source ranges (`internal-only@file`), so it is not reachable publicly. |

Logs are JSON-per-line from every service (api, traefik) — point your
collector at the Docker log driver.

### Backups

PostgreSQL data lives in the `postgres-data` volume:

```bash
docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup-$(date +%F).sql.gz
```

Schedule it (cron/systemd timer) and ship the dumps off-host. Redis holds
only rate-limit counters in phase 1 — it needs no backup.

### Certificates

Traefik stores ACME material in the `letsencrypt` volume and renews
automatically. Losing the volume is harmless (certificates are re-issued,
subject to Let's Encrypt rate limits).

## 6. Scaling and hardening checklist

- `docker compose up -d --scale api=3` — the API is stateless (JWT auth,
  shared state in PostgreSQL/Redis) and Traefik load-balances replicas;
  the Redis rate-limiter stays correct across replicas.
- Move PostgreSQL to managed hosting when load or durability demands it —
  change `PB_API_DATABASE_URL`, drop the bundled service.
- Add off-host log shipping and Prometheus scraping of `/metrics`.
- Keep the host patched; expose nothing but 80/443 (`ufw allow 80,443/tcp`).

## 7. Rollback

Images are rebuilt from git; to roll back, check out the previous tag/commit
and `up -d --build` again. Down-migrations exist (`alembic downgrade -1`) but
prefer roll-forward fixes; take a database backup before any risky release.
