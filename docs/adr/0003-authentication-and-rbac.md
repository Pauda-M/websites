# ADR-0003: Authentication and RBAC

## Status

Accepted — 2026-07-13

## Context

The platform needs authentication and authorization that work for a stateless,
horizontally scalable API (no server-side session affinity), that are safe by
default (governance mandates password hashing, secure secret handling, and
authorization), and that leave room to grow into fine-grained permissions and
server-side token revocation without a breaking change to the token format.

## Decision

**Tokens.** Authentication uses signed **JWTs** (HS256), issued and verified in
`apps/api/src/pb_api/core/security.py`:

- Two token types with a `type` claim: **access** (default 15 minutes,
  `access_token_expire_minutes`) and **refresh** (default 14 days,
  `refresh_token_expire_minutes`). `decode_token(..., expected_type=...)`
  rejects a token presented as the wrong type.
- Every token carries a random `jti` (UUID4) and an `iss` claim set to
  `app_name` (`pb-api`). Decoding validates the issuer and requires the
  `sub`, `exp`, `iat`, and `type` claims to be present.
- The access token carries the user's `role` claim for RBAC; refresh tokens do
  not (a refresh re-reads the authoritative role from the database).

**Passwords.** Hashing is **Argon2id** via `pwdlib` (`PasswordHash.recommended()`).
Because hashing is CPU-bound (~70 ms), it is offloaded from the event loop with
`run_in_threadpool` in `services/users.py`. Authentication of an unknown user
still burns hashing time (`dummy_verify`) to blunt timing-based user
enumeration.

**RBAC.** Roles are `admin`, `staff`, `client` (`db/models/user.py`,
`UserRole`). Authorization is a dependency-injection guard: `require_roles(...)`
in `api/deps.py` returns a FastAPI dependency that reads the current user
(resolved from the access token, then loaded from the database and checked for
`is_active`) and returns 403 unless the user holds one of the required roles.
The role in the token is a convenience; the **database record is
authoritative** — `get_current_user` always loads the user. Example:
`GET /api/v1/users` is guarded by `require_roles(UserRole.ADMIN)`.

**Provisioning.** Self-service `POST /api/v1/auth/register` only ever creates
`client` users (`create_user` defaults `role=UserRole.CLIENT`). Privileged
accounts are provisioned out-of-band via the CLI:
`python -m pb_api.cli create-admin --email ... --full-name ...`
(`--role admin|staff`, password auto-generated and printed once if omitted).

## Alternatives Considered

- **Server-side sessions with cookies.** Simple revocation and no token-in-JS
  exposure, but requires shared session storage and affinity/lookup on every
  request, working against the stateless, horizontally scalable API. Rejected
  for phase 1; the `jti` claim keeps a revocation store on the table later.
- **Delegated OAuth / OIDC provider (Auth0, Cognito, ...).** Offloads
  credential handling and MFA, but adds an external dependency and cost, and is
  overkill for first-party accounts at this stage. Rejected now; the token model
  does not preclude federating later.
- **Opaque tokens with a central introspection store.** Trivial revocation, but
  every request pays a store lookup and needs that store highly available —
  reintroducing the statefulness JWTs avoid. Rejected in favour of short-lived
  self-contained access tokens.

## Consequences

- The API is stateless and scales horizontally: any replica can validate a token
  with the shared secret, no session store required (`docs/DEPLOYMENT.md`
  documents `--scale api=N`).
- Access tokens cannot be revoked before they expire; the 15-minute lifetime
  bounds the exposure window, and clients rotate via
  `POST /api/v1/auth/refresh`.
- The signing secret is load-bearing: production boot fails fast if
  `PB_API_SECRET_KEY` is short or looks like a placeholder (see ADR-0007).
- Argon2id is intentionally expensive; offloading to the threadpool keeps
  concurrent requests responsive while a password is hashed.
- Privilege escalation via the public API is impossible by construction —
  elevated roles exist only through the CLI.

## Future Considerations

- A **token revocation / session store keyed by `jti`** (Redis or PostgreSQL) to
  support logout-everywhere and refresh-token rotation with reuse detection. The
  `jti` and issuer claims are already present so this lands without a
  token-format change.
- **Fine-grained permissions** layered under the existing role dependency
  (permission tables consulted inside `require_roles`-style guards), noted in
  `UserRole` as a later phase.
- Optional MFA and federated identity for first-party accounts if the customer
  base demands it.
