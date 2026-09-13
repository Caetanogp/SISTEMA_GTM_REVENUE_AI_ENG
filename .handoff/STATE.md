---
agent: codex
updated_at: 2026-09-13
branch: feature/SPEC-005-crm-attribution-model
spec: SPEC-005-crm-attribution-model
phase: "Item 8 complete; Item 9 ready"
status: in progress
---

# Current state

## Goal

Implement the PDF-aligned CRM attribution foundation: campaigns, touchpoints, source metadata,
opportunity status and complete account/contact interaction relationships, without starting RAG,
LLM, UI, analytics or agent-tool work.

## Now

SPEC-005 Item 8 is committed, evidenced and accepted by the autonomous gate. The local PostgreSQL
database is at repaired head `f6a8c0d2b5e7`, `alembic check` is clean, and the gate baseline advanced
to `1734abc` for Item 9. No autonomous supervisor is currently running.

## Done

- `2f8b190 fix(persistence): reconcile published migration history` added forward revision
  `f6a8c0d2b5e7`, preserved generic deduplication history, copied legacy typed data, aligned ORM and
  Alembic metadata, and fixed revert event type resolution. Isolated legacy/current migration tests
  passed (4), migration round-trip tests passed (5 total), and existing ingestion, deduplication and
  prioritization integration tests passed (19). `alembic check` reported no new operations.
- `1734abc docs(spec): record item 8 compatibility evidence` checked Item 8 only after its code
  commit and green gate. The following gate advanced to Item 9 with baseline `1734abc` and no halt.
- `2fa27cc docs(persistence): approve migration history reconciliation` recorded the user-approved
  design in the active plan and ADR-0009. Its exact three-path baseline rollover exited 0.
- Items 1-7 remain committed and evidenced in the active `tasks.md`; detailed history stays in git.

## Next

1. Implement Item 9 relationship, lifecycle, idempotency and tenant-isolation integration coverage.
2. Run Item 10 adversarial, traceability and offline-eval verification.
3. Complete Item 11 evidence, full gate and handoff closeout.

## Gotchas

- The executor may not edit the queue, gate, supervisor, AGENTS.md, authorization artifacts or main.
- Docker PostgreSQL and Redis are required only for Item 7 and later integration items.
- Existing unit-of-work boundaries remain unchanged: the adapters flush but never commit.
- Applied revision `b7c9d1e2f304` is immutable; repair only through later forward revisions.
- Preserved generic deduplication objects are audit compatibility data, not current write targets.
- Product scope is fixed by SPEC-005; new statuses, attribution algorithms, external connectors or
  agent exposure require a deliberate scope change.

## Resume

```powershell
git status --short --branch
python scripts/autonomous_gate.py
```

## Open questions

- None. The user approved the forward-only reconciliation in Plan Mode on 2026-09-13.
