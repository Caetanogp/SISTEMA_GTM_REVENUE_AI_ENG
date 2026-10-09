# Autonomous work queue

The only source of work for the SPEC-010 closeout loop. Items run in order and remain inside
their declared file scope. `scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-010-research-and-outreach/tasks.md`

The first eighteen items below record implementation work already completed before this queue was
materialized. They are retained so the deterministic gate can align its task counter. Item 19 is
the only remaining closeout item.

## Item 1 - Approved SPEC-010 contract
- **Scope:** `docs/specs/SPEC-010-research-and-outreach/`
- **Closes:** 1 tasks.md checkbox

## Item 2 - Domain outreach values
- **Scope:** `packages/core/revops/domain/`
- **Closes:** 1 tasks.md checkbox

## Item 3 - Application DTOs and ports
- **Scope:** `packages/core/revops/application/`
- **Closes:** 1 tasks.md checkbox

## Item 4 - Bounded research policy
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 5 - Offline adapters
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 6 - Research use case
- **Scope:** `packages/core/revops/application/`
- **Closes:** 1 tasks.md checkbox

## Item 7 - CRM and RAG context
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 8 - Grounded follow-up generation
- **Scope:** `packages/core/revops/application/`
- **Closes:** 1 tasks.md checkbox

## Item 9 - Tool registration
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 10 - Result endpoint
- **Scope:** `apps/api/`
- **Closes:** 1 tasks.md checkbox

## Item 11 - Offline evaluations
- **Scope:** `evals/`
- **Closes:** 1 tasks.md checkbox

## Item 12 - Runtime v2 selection
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 13 - Runtime v2 reservation
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 14 - Runtime v2 execution
- **Scope:** `packages/core/revops/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox

## Item 15 - Runtime v2 completion
- **Scope:** `packages/core/revops/application/`
- **Closes:** 1 tasks.md checkbox

## Item 16 - Security and adversarial evidence
- **Scope:** `tests/adversarial/`
- **Closes:** 1 tasks.md checkbox

## Item 17 - Traceability evidence
- **Scope:** `docs/requirements/`
- **Closes:** 1 tasks.md checkbox

## Item 18 - Legacy compatibility
- **Scope:** `tests/integration/`
- **Closes:** 1 tasks.md checkbox

## Item 19 - Bounded SPEC-010 pilot and verification
- **Scope:** `docs/specs/SPEC-010-research-and-outreach/`, `docs/requirements/`, `.handoff/`
- **Requires:** the pilot must use the v2 lifecycle and the existing integration database
- **Closes:** 1 tasks.md checkbox
- **What:** run the focused v2 lifecycle pilot, full verification commands, and record concrete evidence in the handoff without changing product scope or controls.
- **Done when:** the focused pilot, full gate, and clean-tree checks pass; no overnight loop is needed after this item because the approved SPEC-010 implementation queue is exhausted.

## Loop rules

- Never edit this queue, the gate, supervisor controls, or `AGENTS.md` from an executor item.
- Return `architecture_required` for an uncovered component shape, state-machine edge, or other
  decision with multiple defensible implementations; return `HUMAN_REQUIRED` for product scope,
  security, dependency, destructive, external-action, or unverifiable decisions.
- No push, merge, work on `main`/`develop`, skipped tests, weakened checks, or checkout temp files.
- Commit one logical item before checking its task evidence.
- This queue is a bounded closeout queue, not an overnight feature-development queue. A future
  long loop requires a new approved spec with real unchecked implementation tasks.
