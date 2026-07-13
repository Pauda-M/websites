# ADR-0007: Configuration and secrets

## Status

Accepted — 2026-07-13

## Context

The same images must run across development, staging, and production, differing
only by configuration. Governance forbids hardcoding secrets and requires
production boot to fail fast on placeholder secrets. Configuration therefore has
to come entirely from the environment, be strongly typed and validated, and make
a misconfigured production deploy fail loudly at startup rather than quietly at
runtime.

## Decision

**Twelve-factor, environment-only configuration.** All API settings are a
**Pydantic Settings** class in `apps/api/src/pb_api/core/config.py` sourced from
environment variables with the **`PB_API_`** prefix (e.g.
`PB_API_SECRET_KEY`, `PB_API_RATE_LIMIT_PER_MINUTE`). A few cross-stack values
are accepted under either name via `AliasChoices`, so one variable can be shared
across the compose services: `environment`
(`PB_API_ENVIRONMENT` | `PB_ENVIRONMENT`), `database_url`
(`PB_API_DATABASE_URL` | `DATABASE_URL`), and `redis_url`
(`PB_API_REDIS_URL` | `REDIS_URL`). The service-specific `PB_API_*` name wins;
the shared name is the fallback. Configuration is read only through this class —
no `os.environ` access elsewhere.

**Production-hardening validation.** A Pydantic `model_validator(mode="after")`
runs only when `environment == "production"` and **refuses to boot** if any of
these hold:

- `PB_API_SECRET_KEY` is shorter than 32 characters, or
- it contains a placeholder marker (`dev-only`, `change-me`, `changeme`,
  `secret-key`, `example`), or
- `*` is present in the CORS origins list, or
- `database_url` does not start with `postgresql`.

**Secrets never in git.** `.env` files are git-ignored; `.env.example` documents
every variable with dev-only defaults and states plainly that those are dev
defaults, to be replaced by injected secrets in staging/production. The
application only ever reads the environment, so moving to a secret store changes
nothing in code.

## Alternatives Considered

- **Config files (YAML/TOML/INI) per environment.** Explicit and reviewable, but
  invites committing environment-specific files (and secrets) and diverges from
  the twelve-factor model that the identical-images-everywhere deployment
  depends on. Rejected.
- **An external secret manager (Vault/SSM/Doppler) integrated now.** The right
  long-term answer, but adds an operational dependency and client code before it
  is needed; the phase-1 mechanism is a `chmod 600` `.env` on the host. Rejected
  as premature — the env-only contract makes adopting a manager a no-code change
  later.
- **Reading `os.environ` ad hoc where needed.** Zero ceremony, but scatters
  configuration, defeats typing/validation, and makes the production guardrails
  impossible to enforce centrally. Rejected.

## Consequences

- A production misconfiguration (placeholder secret, wildcard CORS, non-Postgres
  URL) is caught at startup with a clear error, not discovered in production
  traffic — see `docs/TROUBLESHOOTING.md`.
- Configuration precedence is a real environment variable over a value in a
  `.env` file; the compose stack sets variables explicitly.
- Adding a setting is a one-line change in `config.py` plus an entry in
  `.env.example`; there is exactly one place to look.
- The env-only contract keeps the door open to any secret store without code
  changes, at the cost of relying on host/orchestrator hygiene for `.env` in
  phase 1.
- Because `NEXT_PUBLIC_*` web values are build-time inlined, they are not part of
  this runtime-config model — see ADR-0004 and `docs/CONFIGURATION.md`.

## Future Considerations

- **External secret-store injection** (Vault, AWS SSM/Secrets Manager, Docker
  secrets) feeding the same environment variables into the containers — an
  operational change, not a code change.
- Per-environment schema variants or stricter staging validation if drift
  between environments becomes a source of incidents.
- A configuration dump/validation subcommand to verify a target environment
  before deploy.
