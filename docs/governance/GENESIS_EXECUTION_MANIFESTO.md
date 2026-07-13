# PB GENESIS — EXECUTION MANIFESTO

**Version 1.0**

> This is the primary engineering constitution of PB Genesis. It is the highest
> priority engineering document after the Product Vision. Every future AI software
> engineering agent — Claude Code, Codex, ChatGPT, Cursor, Gemini, Windsurf, or any
> other — must read this document **in its entirety** before writing a single line
> of code. If an implementation conflicts with this manifesto, **the implementation
> is wrong.**

---

## Purpose

This document defines the engineering philosophy, execution model, governance rules,
and autonomous behaviour expected from every AI software engineering agent working on
PB Genesis. Every implementation must comply with this manifesto.

If implementation conflicts with this document, the implementation is wrong.

## Mission

Genesis is not another AI application. Genesis is an **Autonomous Digital Workforce
Platform**. The objective is to create software that behaves like an intelligent,
continuously improving organization. Every engineering decision must move Genesis
closer to this vision.

## Engineering Philosophy

We optimize for:

- Long-term maintainability
- Production quality
- Modularity
- Observability
- Replaceability
- Reliability
- Scalability
- Security
- Knowledge preservation
- Continuous improvement

We never optimize for:

- Quick hacks
- Temporary solutions
- Placeholder implementations
- Hardcoded behaviour
- Vendor lock-in

## First Principles

- Everything is an **Event**.
- Everything produces **Knowledge**.
- Everything produces **Memory**.
- Everything can be **Learned from**.
- Everything can be **Improved**.
- Everything must be **Observable**.

## Architecture

Genesis is built from independent **bounded contexts**. Every bounded context owns:

- its data
- its business rules
- its APIs
- its documentation
- its tests
- its events

No module may directly access another module's internal implementation.
Communication occurs through defined interfaces.

## Cognitive Principle

Genesis is **NOT prompt driven**. Genesis is **memory driven**.

Prompt generation is a consequence of: Identity, Mission, Policies, Goals, Memory,
Knowledge, Current Context, Events, and Reflection.

Every response must originate from cognition, not from static prompting.

## Autonomous Execution Loop

Every implementation follows:

```
Observe → Analyse → Plan → Implement → Compile → Test → Measure → Review → Improve → Repeat
```

Do not terminate after implementation. Terminate only when acceptance criteria pass.

## Self Review

Every completed task must include self review. Review: architecture, naming,
duplication, performance, security, maintainability, test coverage, documentation,
and complexity. **Refactor before completion.**

## Quality Gates

Software is never complete until:

- Build succeeds
- Lint succeeds
- Formatting succeeds
- Type checking succeeds
- Tests succeed
- Documentation updated
- Architecture remains consistent
- No TODOs
- No placeholders
- No dead code
- No duplicated logic

## No Placeholder Policy

Never create: fake implementations, TODO endpoints, temporary logic, future
implementation comments, or mock production behaviour.

**Everything committed to main must be functional.**

## Testing Principle

Every feature requires: Unit Tests, Integration Tests, End-to-End Tests (where
appropriate), Regression Tests, and Performance Tests (where appropriate).

Tests are first-class citizens.

## Documentation

Every subsystem requires: Architecture, Developer Guide, Operations Guide, API
documentation, ADR, Sequence diagrams, Class diagrams, and Deployment instructions.

## Security

Always assume production.

Never hardcode: Secrets, Passwords, API Keys, Certificates, Tokens.

Always validate: Input, Permissions, Authority, Identity, Audit, Encryption.

## AI Engineering Behaviour

Every AI engineer should: challenge assumptions, recommend improvements, reduce
complexity, avoid unnecessary dependencies, protect architectural integrity, and
identify technical debt.

Every AI engineer must never: fabricate success, fabricate test results, or hide
failures.

## Knowledge Preservation

Every engineering decision should increase organizational knowledge. Create ADRs,
explain tradeoffs, document reasoning, and record lessons learned. Future engineers
should understand **WHY** decisions exist.

## Learning

Genesis continuously improves. Improvement follows:

```
Observation → Measurement → Hypothesis → Experiment → Evaluation → Deployment → Measurement → Knowledge
```

No improvement may bypass evaluation.

## ML Principle

Foundation models are **external intelligence**. Genesis owns: Memory, Knowledge,
Planning, Reasoning, Workflow, Reflection, ML models, Knowledge Graph, and Business
Intelligence.

The platform must remain **model independent**.

## Event Sourcing

Everything important becomes an immutable event. Events are never modified.
Corrections create new events. History is preserved.

## Memory

Memory is the company's most valuable asset. Memory must survive: LLM replacement,
database migration, infrastructure migration, and version upgrades.

Vendors may change. **Knowledge must not.**

## Modularity

Every module should be replaceable. Every provider should be abstracted. Every
dependency should be isolated. Genesis must never depend entirely on one vendor.

## Autonomy Limits

Genesis **may** autonomously: Read, Analyse, Plan, Summarize, Categorize, Schedule,
Generate drafts, Retrieve memory, Generate reports, and Recommend improvements.

Genesis **must not** autonomously: Approve contracts, Modify pricing, Transfer money,
Delete critical information, Deploy production changes without a configured approval
policy, or Commit legal obligations.

Authority is always policy driven.

## Continuous Improvement

Every implementation should leave the repository better than it was found. Reduce
complexity. Increase reuse. Improve documentation, tests, architecture, naming,
performance, and observability.

## Engineering Culture

Engineers do not write software. Engineers build organizations. Genesis is an
organization. Every module should behave like one department inside that organization.

## Success Metric

Success is **not** measured by lines of code, number of features, or commits.

Success **is** measured by: Reliability, Customer value, Maintainability, Learning,
Revenue generated, Operational excellence, and Knowledge accumulated.

## Final Principle

Every decision should answer one question:

> **"Will this make Genesis a better autonomous company tomorrow than it is today?"**

If the answer is no, do not implement it.

---

## Manifesto Initialization (for every Epic)

Before implementing any future Epic, perform the following initialization sequence.

**Manifesto Initialization** — Read this manifesto in its entirety and treat it as the
primary engineering constitution. From this point forward, every architectural,
implementation, testing, documentation, and deployment decision must align with it.

**Pre-Implementation Validation** — Before beginning implementation of any Epic:

- Validate the Epic against the manifesto.
- Identify any architectural conflicts.
- Resolve conflicts in favor of the manifesto whenever possible.
- If a deviation is technically unavoidable, document it clearly in an ADR, including:
  Context, Reason, Alternatives Considered, Impact, and Future Resolution Strategy.

**Engineering Discipline** — Before writing any code: review existing architecture,
check for reusable components, avoid duplicate functionality, verify bounded-context
ownership, verify dependency direction, verify security implications, verify
observability requirements, and verify testing requirements.

**Continuous Self-Review** — During implementation: continuously compare the
implementation against the manifesto, challenge unnecessary complexity, simplify where
possible, prefer reusable abstractions over one-off implementations, and preserve
architectural consistency.

**Completion Validation** — Before declaring an Epic complete: confirm compliance with
the manifesto, confirm documentation has been updated, confirm ADRs have been created
for significant decisions, confirm tests/linting/formatting/type-checking all pass, and
confirm there are no known architectural violations.

An Epic is **not complete** until it satisfies both its own acceptance criteria **and**
the requirements defined by this manifesto. The long-term architectural integrity of PB
Genesis always takes precedence over implementation speed.
