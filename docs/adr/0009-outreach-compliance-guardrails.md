# ADR-0009: Outreach compliance guardrails

## Status

Accepted — 2026-07-13

## Context

`AI_DEPLOY_AUTHORIZATION.md` ("Legal and compliance") mandates that any feature
which communicates with customers or prospects must:

- maintain suppression and opt-out lists,
- prevent duplicate outreach,
- log outreach history,
- support configurable compliance rules,
- support human review before first contact by default, and
- avoid deceptive or misleading messaging.

The platform is designed to include an **Outbound Sales Engine** (see ADR-0008),
which contacts people and is therefore squarely in scope. That module is not
built yet. A policy that lives only in prose can be forgotten by the (human or
AI) engineer who eventually implements outreach. The requirement needs to be
attached to the code in a form that a future implementation cannot quietly ship
without.

## Decision

The six controls are encoded as a machine-readable constant,
`OUTREACH_COMPLIANCE_CONTROLS`, in
`apps/api/src/pb_api/platform/modules.py`:

```
"maintain-suppression-and-opt-out-lists"
"prevent-duplicate-outreach"
"log-outreach-history"
"configurable-compliance-rules"
"human-review-before-first-contact-by-default"
"no-deceptive-or-misleading-messaging"
```

Every outreach-capable module in the registry carries these controls in its
`compliance_controls` field. Today that is the **Outbound Sales Engine**
(`slug="outbound-sales"`, `/api/v1/outbound`), whose description records that it
"contacts people, so it is gated by the outreach compliance controls and must
not ship without them." The manifest endpoint
(`GET /api/v1/platform/modules`) exposes the controls so they are discoverable.

The guarantee is enforced by tests in `apps/api/tests/test_platform.py`:

- `test_outreach_modules_carry_all_compliance_controls` asserts that every
  module returned by `outreach_modules()` carries the **full** set of controls.
- `test_non_outreach_modules_have_no_controls` asserts that non-outreach modules
  carry none (so the marker means what it says).

Because these tests are part of the required `make test` suite, an outreach
module cannot be added or shipped with a missing control without turning the
local build red.

## Alternatives Considered

- **Doc-only policy.** Simple, but relies on every future implementer reading and
  remembering the governance document; nothing fails if a control is skipped.
  Rejected as insufficient for a legal/compliance requirement — the whole point
  is a guarantee, not a reminder.
- **Runtime-only checks (assert controls at send time, no declaration).**
  Necessary eventually, but with no build-time declaration a module could be
  merged and deployed with the checks absent, and the gap would only surface in
  production. Rejected as the sole mechanism; the declarative marker + test
  catches it before merge. A runtime gate is complementary future work.

## Consequences

- The compliance requirement is expressed as code and defended by tests, so it
  cannot be silently dropped when the Outbound Sales Engine is built.
- The controls are discoverable at runtime via the module manifest, useful for
  audits and internal admin surfaces.
- The marker declares intent; it does not itself implement suppression lists,
  dedupe, logging, review workflows, or messaging checks. Those must be built by
  the outreach module — this ADR guarantees they are named and required, not
  that they exist yet.
- Any new module that contacts people must be added with the full control set,
  or the suite fails — a deliberate, low-friction speed bump on outreach
  features.

## Future Considerations

- A **compliance-gate service or middleware** enforced at outreach send time
  (checking suppression/opt-out state, dedupe, and logging every send), so the
  declared controls are backed by runtime enforcement, not only a build-time
  assertion.
- Configurable, per-tenant compliance rule sets once multi-tenancy lands.
- An audit trail / reporting surface over logged outreach history to evidence
  compliance.
