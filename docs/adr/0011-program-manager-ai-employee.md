# ADR-0011: Program Manager AI Employee

## Status

Accepted — 2026-07-13

## Context

Genesis Epic 008 requires the **Program Manager**: the first fully functional AI
Employee and the reference implementation every future AI Employee follows. It is
not a chatbot — it is an autonomous business employee that owns customer
communication, opportunity and project management, proposal preparation,
scheduling, follow-ups, and organizational memory, operating within explicit
authority limits.

The Cognitive Core (ADR-0010) already provides the cognitive operating system:
tenant-scoped memory, hierarchical goals, deterministic planning inputs, a policy
engine, reflection, an agent/tool registry, and an append-only event store. Epic
008 must deliver a role — a *worker* — on top of that substrate without
re-implementing any of it, and must do so as a clean, independently-reasoned
module so the pattern is reusable.

Several forces shaped how this landed:

- The foundation reserves loosely-coupled module namespaces (ADR-0008) and requires
  governed autonomy with human-in-the-loop controls (ADR-0009). An AI Employee is
  exactly where those controls become concrete.
- The Cognitive Core is a *capability* layer, not a worker. Placing the Program
  Manager inside `pb_api/cognitive/` would conflate "the cognition every employee
  shares" with "one specific employee." The two must stay separate.
- The specification names outward actions — sending email, booking meetings,
  sending proposals — but Genesis mandates no vendor lock-in and depends on ports,
  never vendors (`004_Company_Brain.md`, `012_Security.md`). The Program Manager has
  to be fully functional *before* any channel adapter exists.
- Autonomy must be bounded and auditable from first boot: every consequential
  action needs an authority decision and an immutable event, and nothing may exceed
  its bound silently.

## Decision

**Placement.** AI Employees are a top-level bounded context at
`apps/api/src/pb_api/agents/`, and the Program Manager lives at
`apps/api/src/pb_api/agents/program_manager/`, addressable at
`/api/v1/agents/program-manager`. `pb_api/cognitive/` stays the shared cognitive
capability; `pb_api/agents/` holds the workers that consume it.

**Composition over re-implementation.** The `ProgramManager` composition root wires
a `CognitiveCore` plus the Program Manager's own repositories and services from one
`AsyncSession`. Memory, goals, context/prompt assembly, policy evaluation,
reflection, and events are all delegated to the Cognitive Core. The module adds only
what is genuinely PM-specific.

**Layering.** Domain (pure Pydantic) → Application (services + the lifecycle
orchestrator) → Infrastructure (tenant-scoped async repositories) → API (FastAPI),
mirroring the Cognitive Core so the codebase reads uniformly.

**The cognitive lifecycle.** A run advances through a governed state machine —
Observe → Understand → Retrieve Memory → Determine Goal → Build Context → Reason →
Plan → Execute → Reflect → Store Memory → Schedule Next — with two off-path states,
Awaiting Approval and Error. Each run is persisted as a `PMRun` with the states it
visited and a `PMTask` per executed step, so every autonomous decision is
reconstructable from the runs plus the event log.

**Authority (L0/L1/L2) delegated to the policy engine.** The Program Manager
operates at one of three coarse tiers — `OBSERVE_ONLY` (L0), `ACT_WITH_APPROVAL`
(L1), `ACT_BOUNDED` (L2) — mapped onto the Cognitive Core's A0–A5 levels. It does
**not** re-implement policy evaluation: it seeds a default, tenant-scoped policy set
(one ALLOW per catalogue action, gated at that action's required authority) and lets
the Core's deterministic engine decide. An ALLOW escalates to REQUIRE_APPROVAL when
the actor's tier is below the policy's minimum authority; an action with no matching
policy is denied. Execution stops at the first step that requires approval — the
Program Manager never performs a partial outward action past its bound.

**Planning specialised, not duplicated.** `PMPlanStep` carries objective,
dependencies, required tools, risk, expected outcome, fallback, and the authority it
needs — fields the generic `cognitive.Plan` does not model. The PM therefore keeps
its own richer plan aggregate rather than duplicating the Core's planning logic.

**Transport is a port.** All CRM, scheduling, and proposal-drafting effects are real
and persisted. Outward-transport actions (send a message, book externally, send a
proposal) record the prepared artifact and emit the event; the transmission itself
is a channel/calendar port a future adapter fulfils. This is preparation the
Program Manager genuinely owns, with transport as an explicit boundary — not a mock.

**One scheduling primitive.** Every piece of deferred work — follow-up, task,
reminder, review — is one `ScheduledAction`. The FollowUpEngine is a thin façade over
it (cadences 24h/72h/7d/30d, or custom); there is no second timer.

## Alternatives Considered

- **Build the Program Manager inside `pb_api/cognitive/`.** Rejected: it conflates the
  shared cognitive capability with one specific worker and would make the next AI
  Employee harder to place cleanly. A dedicated `agents/` namespace keeps the boundary.
- **Re-implement policy/authority logic in the PM.** Rejected as duplication (a
  governance violation) and as a second source of truth for decisions. Mapping L0–L2
  onto A0–A5 and delegating to the Core's engine keeps evaluation deterministic and
  singular.
- **A separate follow-up table and timer.** Rejected: two mechanisms for deferred work
  drift apart. A single `ScheduledAction` with a thin cadence façade keeps every future
  action visible, cancellable, and executable through one path.
- **LLM-driven planning/intent now.** Deferred: like the Cognitive Core's deterministic
  ranker and embeddings, the planner and intent classifier are real, testable,
  dependency-free implementations. A learned planner can augment them later without
  changing the contract.
- **Stub outward actions (fake sends).** Rejected as a mock. Recording the prepared
  artifact and emitting the event — with transport behind a port — is honest and leaves
  a real audit trail.

## Consequences

- The platform gains a complete, tested AI Employee: 13 tenant-scoped tables (Alembic
  `0003`), an eleven-endpoint-plus HTTP surface under `/api/v1/agents/program-manager`,
  and PM business metrics (`pm_runs_total`, `pm_approvals_requested_total`,
  `pm_run_duration_seconds`) on the existing `/metrics` registry.
- Governed autonomy is concrete: nothing outward-facing happens above the configured
  tier without a human approval, and every run, task, goal, plan, and action is an
  auditable record plus an event.
- The module is the template for future AI Employees — the `agents/` placement, the
  compose-the-Cognitive-Core pattern, the lifecycle machine, and the authority mapping
  are all reusable.
- The suite still runs on SQLite with no external services; production runs PostgreSQL
  unchanged, via portable column types.
- A real deployment still needs channel/calendar adapters to *transmit* prepared
  artifacts; until then those actions stop at "prepared + event emitted."

## Future Considerations

- Channel and calendar **port adapters** (email, messaging, calendaring) to transmit
  prepared artifacts; the application interface does not change when they land.
- A learned **planner** and **intent classifier** to replace the deterministic
  defaults, behind the same `PMPlan`/`PMGoalType` contracts.
- **Resuming** an approved run automatically (today, approval clears the awaiting flag
  and the approved action is re-driven on the subject's next run).
- Row-level tenant isolation once the multi-tenancy delta (`000_Glossary.md` §13) lands,
  hardening the application-level tenant scoping the module already enforces.
- Additional AI Employees (e.g. Outbound Sales, Support) built on this reference,
  collaborating through the shared Company Brain and event bus.
