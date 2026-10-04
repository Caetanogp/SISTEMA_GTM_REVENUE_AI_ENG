---
agent: codex
updated_at: 2026-10-04
branch: feature/SPEC-008-context-retrieval
spec: SPEC-008-context-retrieval
phase: "Item 3 exact retrieval adapter implemented and verified"
status: pilot_complete_item_3
---

# Current state

## Goal

Implement PDF-aligned task-scoped knowledge retrieval in SPEC-008.

## Now

SPEC-008 items 1-3 are complete: 9 of 15 task checkboxes are checked. Item 4 is the active queue
item. No autonomous loop is running. The bounded Item 3 validation was completed in the main
checkout because the earlier supervisor architecture review halted before implementation.

## Done

- Item 3 exact retrieval adapter: active embedding-space resolution, tenant-scoped platform and
  organization selection, organization override before ranking, active revision and ready-state
  filtering, materialized eligible sources, exact pgvector cosine ranking, deterministic ordering,
  complete provenance, zero-vector integrity checks, and sanitized persistence errors. Commit
  `e02e529`; follow-up override evidence and four checked task lines in `096255c`.
- Application/domain hardening: float32-representable query validation, overflow-safe norm checks,
  zero-vector rejection, fixed public failure codes, and suppressed provider/SQL causes. Commit
  `e02e529`.
- Approved design and autonomous controls: exact retrieval decision in SPEC-008 docs and ADR-0016,
  item 3 scope expansion, UTF-8/local-checkout runtime environment, `ready_for_gate`, and
  `StopAfterItem`. Commit `737b285`; formal baseline rollover passed for six exact control paths.
- Focused evidence: 98 unit tests passed, the PostgreSQL retrieval integration passed with a
  synthetic platform/org override where the platform vector scored higher, and the item 3 gate
  reported Ruff, mypy, import-linter, unit/architecture tests, and agent docs all OK.
- Full verification: `pytest tests/unit tests/architecture -q` 440 passed; `pytest
  tests/integration -q` 46 passed; `pytest tests/adversarial -q` 13 passed; Ruff and format passed;
  mypy passed for 172 source files; import-linter kept 4 contracts; agent docs passed; all offline
  eval suites remained at 1.00; gitleaks reported no leaks.

## Next

1. Implement Item 4 internal composition-root wiring and tenant authorization in a bounded pilot.
2. Run the item 4 gate and inspect the resulting commit before allowing an overnight loop.
3. If item 4 remains architecture-stable and the pilot is green, launch the long loop with the
   checkout-local Python path and optional `-StopAfterItem` only when a bounded run is desired.

## Gotchas

- The working checkout is `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`; the original OneDrive checkout must
  not be used for this development loop.
- The supervisor baseline is `096255c` with done count 9; the ignored gate state is not committed.
- The database used for verification is the synthetic Docker database `revops_item8b`.
- Exact ranking is intentional. HNSW remains in the schema but is not the correctness mechanism for
  tenant filtering and organization override.
- The old architecture-halt entries remain in git history; they do not represent the current
  implementation state.

## Resume

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:DATABASE_URL = 'postgresql+psycopg://revops:revops@localhost:5432/revops_item8b'
python scripts/autonomous_gate.py
```

## Open questions

None for Item 3. Item 4 is the next implementation item; no product-scope or architecture choice
is currently awaiting the user.
