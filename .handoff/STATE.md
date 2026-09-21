---
agent: codex
updated_at: 2026-09-20
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 domain/chunking pilot implemented"
status: in_progress
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

SPEC-005 and SPEC-006 are merged into `develop` and published to `origin/develop`.
SPEC-007 documentation and queue are materialized on `feature/SPEC-007-rag-ingestion`.
The first pilot exposed a Windows child-temp-path regression. The supervisor fix is committed;
the domain/chunking implementation and tests are now complete. A second interrupted run generated
one new checkout temp artifact that must be removed before the gate can certify the item.

## Done

- `c237b95` is the verified SPEC-006 integration head in `develop`.
- `0e73e66` moved supervisor temporary allocation outside the checkout and added preflight guards.
- `1adb120` removed child `TEMP/TMP/PYTEST_ADDOPTS` overrides; supervisor tests passed `28 tests`.
- `ab41212` corrected queue coverage counting so Item 1 closes two tasks.
- The residual pilot artifact was confirmed absent with `Test-Path=False` on 2026-09-20.
- Domain/chunking pilot implementation is present in `packages/core/revops/domain/entities/knowledge.py`;
  Ruff, format, mypy, lint-imports, and domain/architecture tests passed (`128 passed`).

## Next

1. Remove the new interrupted-run checkout artifact and confirm a clean tree.
2. Run the gate to certify Item 1 and advance the baseline to the pilot commit.
3. Launch the bounded long loop from Item 2 for remaining SPEC-007 items.

## Gotchas

- Retrieval, memory, and grounded generation are deferred to SPEC-008.
- Supervisor artifacts must remain outside the checkout.
- The live embedding adapter must never silently fall back to fake vectors.
- Do not delete `.handoff/.autonomous_gate_state.json`; use the formal rollover authorization.
- The second pilot process was interrupted after writing the executor files; its code was manually
  validated before task checkboxes were updated.

## Resume

```powershell
git status --short --branch
git log -1 --oneline
python scripts/autonomous_gate.py
```

## Open questions

- None for the agreed SPEC-007 scope.
