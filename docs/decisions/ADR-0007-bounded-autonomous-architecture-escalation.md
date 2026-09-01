# ADR-0007: Use bounded autonomous architecture escalation

- **Status:** accepted
- **Date:** 2026-09-01
- **Context spec:** SPEC-003

## Context

Long Codex runs repeatedly reached legitimate technical design gaps after earlier queue items had
completed. A hard stop protected architecture quality but required the user to return, select the
recommended technical option, and relaunch the same queue. Letting the implementation executor
choose and widen its own scope would remove the interruption by removing the safety boundary.

The CLI can select model and reasoning effort per non-interactive process, but it does not expose a
stable non-interactive switch for the TUI's Plan Mode. The unattended equivalent therefore needs
enforced read-only execution, structured output, independent review, and a deterministic policy.

## Options considered

1. **Keep every architecture gap as a human HALT** - safest and simplest, but prevents an otherwise
   healthy overnight run from resuming after a bounded technical decision.
2. **Let the implementation executor choose and continue** - cheapest and uninterrupted, but the
   same model would define, approve, widen, implement, and judge its own work.
3. **Use an external bounded supervisor** - more process code and strong-model calls, but separates
   implementation, architecture, review, authorization, and deterministic completion.

## Decision

Use an external Codex supervisor. Resolved implementation runs on the configured economical model
at medium reasoning. A clean `architecture_required` outcome invokes a read-only
`gpt-5.6-sol/xhigh` architect and an independent read-only reviewer, for at most two attempts. Only
an approved plan inside the deterministic autonomy policy receives an external, item-bound scope
authorization. The economical executor then resumes with that plan.

Product scope or public-contract invention, dependencies, destructive migration, security or
verification relaxation, external actions, dirty partial implementations, and choices without a
dominant safe recommendation remain `HUMAN_REQUIRED`.

## Consequences

Purely technical Clean Architecture gaps can be resolved without waking the user, while the
executor still cannot authorize itself. Strong-model cost is paid only at an actual escalation and
twice per attempt. Temporary artifacts and scope authorization live outside the checkout.

The loop still cannot guarantee uninterrupted execution: usage limits, OS suspension, repeated
process failures, reviewer disagreement, or a hard-policy decision stop it. The supervisor and its
policy now become control-plane code and require regression tests before changes. Child outcomes
are rejected if a protected control hash changes. A supervisor upgrade during an active queue item
requires a clean, externally authorized, exact-SHA baseline rollover; deleting or silently
rewriting gate state is not an accepted upgrade path.
