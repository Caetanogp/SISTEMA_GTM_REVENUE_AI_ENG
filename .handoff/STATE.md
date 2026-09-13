---
agent: codex
updated_at: 2026-09-13
branch: feature/SPEC-005-crm-attribution-model
spec: SPEC-005-crm-attribution-model
phase: "Item 6 complete; awaiting autonomous gate"
status: in progress
---

# Current state

## Goal

Implement the PDF-aligned CRM attribution foundation: campaigns, touchpoints, source metadata,
opportunity status and complete account/contact interaction relationships, without starting RAG,
LLM, UI, analytics or agent-tool work.

## Now

SPEC-005 Item 6 implementation and its mapped checklist are committed. Run the autonomous gate to
confirm the item transition; do not begin Item 7 in this session.

## Done

- `60ac93f feat(persistence): add attribution repositories` added tenant-scoped Campaign, Contact
  and append-only Touchpoint adapters at
  `packages/core/revops/infrastructure/persistence/repositories.py:202`, `:236` and `:250`.
  `tests/unit/infrastructure/persistence/test_repositories.py:72`, `:79`, `:195`, `:218` and `:242`
  cover structural ports, no history mutation, tenant filters and persisted relationships.
  `pytest tests/unit/infrastructure/persistence/test_repositories.py tests/unit/infrastructure/persistence/test_models.py -q`
  passed (31 passed); scoped Ruff, `ruff format --check`, mypy, `lint-imports` and `git diff --check`
  passed. The commit's pre-commit hooks passed.
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

1. Run `python scripts/autonomous_gate.py` and record its observed result.
2. Start Item 7 only in its separately authorized queue turn; run the Docker migration round-trip.
3. Keep the full verification and traceability closeout for Item 11.

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

- None for Item 6.
