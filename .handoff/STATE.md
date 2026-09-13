---
agent: codex
updated_at: 2026-09-13
branch: feature/SPEC-005-crm-attribution-model
spec: SPEC-005-crm-attribution-model
phase: "Item 10 complete; Item 11 ready"
status: in progress
---

# Current state

## Goal

Implement the PDF-aligned CRM attribution foundation: campaigns, touchpoints, source metadata,
opportunity status and complete account/contact interaction relationships, without starting RAG,
LLM, UI, analytics or agent-tool work.

## Now

SPEC-005 Item 10 is committed and evidenced. `pytest tests/adversarial -q` passed with 11 tests,
the PDF traceability checker passed all 86 rows across pages 1-20, and `python -m evals.gate`
passed tool selection (14/14) and lead scoring (15/15). No autonomous supervisor is currently
running.

## Done

- `324e62d test(security): cover untrusted attribution metadata` added adversarial coverage that
  CRM attribution metadata cannot inject organization ownership or relationship identifiers, and
  added an offline tool-selection case that refuses metadata-based bulk task instructions. The Item
  10 gate (Ruff, mypy, lint-imports, unit/architecture tests and agent docs) was green; adversarial
  tests (11), PDF traceability checker (86 rows) and eval gate (14/14, 15/15) also passed.
- `32e7b78 test(persistence): cover attribution integration behavior` added real PostgreSQL
  coverage for campaign/touchpoint relationship round-trips, tenant-scoped reads, cross-tenant
  relationship rejection, interaction contact/content persistence, explicit opportunity lifecycle
  filtering and documented append-only duplicate touchpoints. The complete integration suite passed
  (36), along with scoped Ruff, mypy and lint-imports. `aa96fae docs(spec): record item 9
  integration evidence` checked Item 9 only after that evidence existed.
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

1. Complete Item 11 evidence, full gate and handoff closeout.

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
