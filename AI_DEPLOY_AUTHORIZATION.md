# AI_DEPLOY_AUTHORIZATION.md

## PB Platform — AI Engineering Governance

**This document is the governing authority for the repository.** Where any
implementation conflicts with this document, this document takes precedence.
It is adopted repo-wide and applies to every change, by any contributor,
human or AI.

> **Read first:** the [Genesis Execution Manifesto](docs/governance/GENESIS_EXECUTION_MANIFESTO.md)
> is the primary engineering constitution of PB Genesis — the highest-priority
> engineering document after the Product Vision. Every AI engineer must read it in
> full before writing any code, and validate every Epic against it. This
> authorization operationalizes the manifesto for this repository; where they
> speak to the same concern, the manifesto's principles govern.

---

## Purpose

This repository authorizes AI software engineering agents (Claude Code,
ChatGPT, Codex, Cursor, Windsurf, Gemini CLI, and equivalent tools) to design,
implement, refactor, test, document, deploy, and maintain this repository.

The objective is to build and maintain production-grade software while
preserving architectural consistency, quality, maintainability, and security.

## Repository

| Field          | Value              |
| -------------- | ------------------ |
| Repository     | PB Platform        |
| Organization   | PB Solutions       |
| Primary domain | pb-solutions.today |

## Engineering philosophy

- The repository is intended for long-term commercial use.
- Every implementation must be production-ready.
- Never implement prototypes.
- Never implement placeholder logic.
- Never intentionally reduce software quality for speed.
- Prefer long-term maintainability over short-term convenience.

## Authorized actions

AI agents may: create new files; modify existing files; delete obsolete files;
refactor architecture; improve performance, maintainability, security,
accessibility, SEO, and observability; create APIs, UI, database migrations,
documentation, infrastructure, CI/CD, Docker configuration, tests, monitoring,
and deployment scripts.

## Autonomous workflow

AI agents operate autonomously. The execution cycle is:

```
Analyse → Plan → Implement → Compile → Test → Fix → Repeat
```

Continue the loop until every acceptance criterion has passed. Do not stop
after the first successful implementation if unresolved issues remain.

## Engineering standards

Every implementation must:

- compile successfully
- pass automated tests
- pass linting
- pass formatting
- pass type checking
- include documentation where appropriate
- follow repository conventions
- avoid duplicated code
- use dependency injection where appropriate
- be modular
- be observable
- be secure by default

## Coding standards

Code must be strongly typed, readable, modular, documented, maintainable,
deterministic where practical, and free from unnecessary complexity.

Avoid: dead code, commented-out code, duplicated logic, magic numbers,
oversized functions, oversized classes, and hidden side effects.

## Testing requirements

Every implemented feature must include appropriate automated testing where
practical. Testing hierarchy: unit → integration → end-to-end → regression.
A feature is not complete until its relevant tests pass.

## Validation loop

After every significant implementation: build → lint → type check → run tests
→ fix failures → repeat. Continue until there are zero known failures. In this
repository the loop is codified as `make lint typecheck test` (plus
`make test-e2e` for cross-service changes) and must pass locally before every
commit — validation is performed on the developer's machine, not a CI service.

## Git workflow

Use small logical commits. Every commit must build successfully, pass tests,
and include documentation updates when behaviour changes. Commit messages
should clearly describe the implemented feature.

## Documentation

Every significant subsystem must include documentation. Repository
documentation includes Architecture, Deployment, Development, Configuration,
Security, Operations, and Troubleshooting. See [`docs/`](docs/) and the
Architecture Decision Records in [`docs/adr/`](docs/adr/).

## Security requirements

Always implement secure defaults:

- input validation
- parameterized database queries
- password hashing
- secure secret handling
- CSRF protection where applicable
- authentication and authorization
- rate limiting
- audit logging and structured logging
- dependency updates
- security headers

**Never hardcode** passwords, API keys, tokens, certificates, or connection
strings. Secrets enter only through the environment; production boot fails
fast on placeholder secrets. See [`docs/SECURITY.md`](docs/SECURITY.md).

## Performance

Prefer efficient algorithms; avoid unnecessary database queries; use caching
appropriately; measure performance before optimization.

## Observability

Every service exposes a health endpoint, a readiness endpoint, a metrics
endpoint, and structured logs.

## Production readiness

Software is complete only when it is deployable, recoverable, observable,
documented, tested, and secure.

## AI behaviour

AI agents should challenge poor architectural decisions, prefer simplicity,
avoid unnecessary dependencies, avoid vendor lock-in unless justified, identify
technical debt, and recommend improvements when beneficial.

AI agents must not invent functionality that cannot be implemented, must not
fabricate test results, and must not claim success without verification. If an
issue cannot be resolved autonomously, the blocker must be documented clearly.

## Acceptance rule

A task is complete only when: all requested functionality is implemented;
automated validation passes; documentation is updated; deployment succeeds;
and no known critical defects remain. Otherwise, continue iterating.

## Legal and compliance

The platform must support lawful business operations. Any feature that
communicates with customers or prospects must:

- maintain suppression and opt-out lists
- prevent duplicate outreach
- log outreach history
- require configurable compliance rules
- support human review before first contact by default
- avoid deceptive or misleading messaging

These controls are encoded as machine-readable requirements on outreach-capable
modules in the platform module registry
(`apps/api/src/pb_api/platform/modules.py`, `OUTREACH_COMPLIANCE_CONTROLS`) and
recorded in [ADR-0009](docs/adr/0009-outreach-compliance-guardrails.md), so a
future implementation cannot ship without satisfying them.

## Guiding principle

**Every change should leave the repository in a better state than it was
found.**
