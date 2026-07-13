# Architecture Decision Records

An **Architecture Decision Record (ADR)** captures a single significant
architectural decision: the context that forced a choice, the decision itself,
the alternatives that were weighed, and the consequences the team accepted.
ADRs are immutable history — once a decision is `Accepted` it is not edited to
reflect a later change of mind. Instead, a new ADR is added that supersedes the
old one, and the old one's `Status` is updated to point at its replacement.

This is where the _why_ lives. `docs/ARCHITECTURE.md` describes the system as it
is; the ADRs explain how it got that way and what was deliberately rejected.

## Folder convention

- Files are named `NNNN-kebab-case-title.md`, where `NNNN` is a zero-padded,
  monotonically increasing number (`0001`, `0002`, ...).
- `0000-adr-template.md` is the starting point for every new record — copy it,
  give it the next number, and fill it in.
- Numbers are never reused. A superseded ADR keeps its number and gains a
  `Superseded by ADR-XXXX` note in its `Status` section.

## Required section structure

Every ADR (the template excepted) uses exactly these H2 sections, in this
order:

1. **Status** — `Proposed`, `Accepted`, `Superseded`, or `Deprecated`, with a
   date.
2. **Context** — the forces at play: requirements, constraints, and the problem
   being solved.
3. **Decision** — what was decided, stated plainly and grounded in the code.
4. **Alternatives Considered** — the options that were rejected and why.
5. **Consequences** — the results, good and bad, that the team accepts.
6. **Future Considerations** — known follow-ups this decision leaves open.

## Records

| Number | Title                                                                    | Status   |
| ------ | ------------------------------------------------------------------------ | -------- |
| 0001   | [Monorepo structure](0001-monorepo-structure.md)                         | Accepted |
| 0002   | [Backend stack](0002-backend-stack.md)                                   | Accepted |
| 0003   | [Authentication and RBAC](0003-authentication-and-rbac.md)               | Accepted |
| 0004   | [Frontend stack](0004-frontend-stack.md)                                 | Accepted |
| 0005   | [Edge and deployment](0005-edge-and-deployment.md)                       | Accepted |
| 0006   | [Observability](0006-observability.md)                                   | Accepted |
| 0007   | [Configuration and secrets](0007-configuration-and-secrets.md)           | Accepted |
| 0008   | [Modular namespace reservation](0008-modular-namespace-reservation.md)   | Accepted |
| 0009   | [Outreach compliance guardrails](0009-outreach-compliance-guardrails.md) | Accepted |
| 0010   | [Cognitive Core](0010-cognitive-core.md)                                 | Accepted |
| 0011   | [Program Manager AI Employee](0011-program-manager-ai-employee.md)       | Accepted |

## Governance

The repository-wide engineering authority is
[`AI_DEPLOY_AUTHORIZATION.md`](../../AI_DEPLOY_AUTHORIZATION.md). Where an ADR
and that document appear to conflict, the governance document wins and the ADR
must be corrected. ADR-0009 in particular exists to encode a governance mandate
in machine-checkable form.
