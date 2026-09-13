---
agent: codex
updated_at: 2026-09-13
branch: feature/SPEC-005-crm-attribution-model
spec: SPEC-005-crm-attribution-model
phase: "Item 8 migration-history reconciliation approved"
status: in progress
---

# Current state

## Goal

Implement the PDF-aligned CRM attribution foundation: campaigns, touchpoints, source metadata,
opportunity status and complete account/contact interaction relationships, without starting RAG,
LLM, UI, analytics or agent-tool work.

## Now

SPEC-005 Item 8 is ready for implementation after a user-approved deliberate design pass. The
approved remedy is a new forward, additive migration after `e4f6a8c0d2b5` that converges both the
original generic deduplication schema and the current typed schema. It preserves legacy objects and
data, validates conflicts and tenant integrity, and never edits `b7c9d1e2f304` again. The decision
is recorded in the active plan and ADR-0009. No implementation has started.

## Done

- `4c91660 test(persistence): verify attribution migration round trip` added the real PostgreSQL
  round-trip proof at `tests/integration/test_attribution_migration_round_trip.py:39` and made the
  attribution migration tolerate historical databases whose recorded `b7c9d1e2f304` revision
  predates its tenant identity constraints at
  `packages/core/revops/infrastructure/persistence/migrations/versions/e4f6a8c0d2b5_add_crm_attribution_schema.py:20`.
  `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` and
  `pytest tests/unit/infrastructure/persistence/test_attribution_migration.py tests/unit/infrastructure/persistence/test_models.py tests/integration/test_attribution_migration_round_trip.py -q`
  passed (14 passed). Scoped Ruff, format, mypy, `lint-imports`, `git diff --check` and the commit
  hooks passed. `python scripts/autonomous_gate.py` exited 1 at the expected Item 8 evidence-path
  checkpoint, without a halt.
- `60ac93f feat(persistence): add attribution repositories` added tenant-scoped Campaign, Contact
  and append-only Touchpoint adapters at
  `packages/core/revops/infrastructure/persistence/repositories.py:202`, `:236` and `:250`.
  `tests/unit/infrastructure/persistence/test_repositories.py:72`, `:79`, `:195`, `:218` and `:242`
  cover structural ports, no history mutation, tenant filters and persisted relationships.
  `pytest tests/unit/infrastructure/persistence/test_repositories.py tests/unit/infrastructure/persistence/test_models.py -q`
  passed (31 passed); scoped Ruff, `ruff format --check`, mypy, `lint-imports` and `git diff --check`
  passed. The commit's pre-commit hooks passed.
- Item 6 gate: `python scripts/autonomous_gate.py` exited 1 at the expected Item 7 evidence-path
  checkpoint; the worktree was clean and no halt was reported.
- `b2bffd3 feat(persistence): add attribution migration` created revision `e4f6a8c0d2b5`, tenant
  foreign keys, indexes and the `open` backfill. Offline SQL and 13 migration/model tests passed.
- `fc929bc feat(persistence): add attribution models` added Campaign and append-only Touchpoint
  models, relationship columns and constrained opportunity status.
- `7a241df feat(application): validate attribution relationships` added tenant-safe relationship
  validation, canonical aliases and the Contact repository port.
- `6c396e3 feat(application): add attribution ports and DTOs` added strict campaign/touchpoint
  DTOs and tenant-scoped repository ports.
- `d92031d feat(domain): add attribution contracts` added pure Campaign, Touchpoint and
  opportunity-status contracts with unit coverage.

## Next

1. Apply the one-time exact-SHA baseline rollover for the approved architecture documentation.
2. Implement and test the additive reconciliation under Item 8's existing code scope.
3. Run the Item 8 gate, then continue integration, security and closeout Items 9-11.

## Gotchas

- The executor may not edit the queue, gate, supervisor, AGENTS.md, authorization artifacts or main.
- Docker PostgreSQL and Redis are required only for Item 7 and later integration items.
- Existing unit-of-work boundaries remain unchanged: the adapters flush but never commit.
- Product scope is fixed by SPEC-005; new statuses, attribution algorithms, external connectors or
  agent exposure require a deliberate scope change.

## Resume

```powershell
git status --short --branch
python scripts/autonomous_gate.py
```

## Open questions

- None. The user approved the forward-only reconciliation in Plan Mode on 2026-09-13.

## Historical pilot halt

The 2026-09-13 three-turn pilot stopped at its configured turn limit after reaching Item 8. It was
not a code or sandbox failure; the long run is a separate authorized execution.

## Autonomous loop HALT (2026-09-13T04:46:00+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. Supervisor reached its maximum of 3 Codex turns

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-09-13T05:04:24+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. Architecture escalation was requested after uncommitted changes; refusing to design over a partial implementation

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
