---
agent: codex
updated_at: 2026-09-22
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 final temp-isolation pilot pending"
status: in_progress
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

SPEC-005 and SPEC-006 are merged into `develop` and published to `origin/develop`.
SPEC-007 documentation and queue are materialized on `feature/SPEC-007-rag-ingestion`.
The domain/chunking implementation and tests are complete. The supervisor and launcher now preserve
native Windows temp variables, remove only the custom pytest override, bound child execution time,
and keep supervisor artifacts outside the checkout. The last interrupted validation left two old
checkout artifacts; they must be removed before the final pilot.

## Done

- `c237b95` is the verified SPEC-006 integration head in `develop`.
- `0e73e66` moved supervisor temporary allocation outside the checkout and added preflight guards.
- `1adb120` removed child `TEMP/TMP/PYTEST_ADDOPTS` overrides; supervisor tests passed `28 tests`.
- `ab41212` corrected queue coverage counting so Item 1 closes two tasks.
- The residual pilot artifact was confirmed absent with `Test-Path=False` on 2026-09-20.
- Domain/chunking pilot implementation is present in `packages/core/revops/domain/entities/knowledge.py`;
  Ruff, format, mypy, lint-imports, and domain/architecture tests passed (`128 passed`).
- Supervisor and launcher regression suites passed (`30 passed`); the latest fix is `9202567`.

## Next

1. Remove `codex-revops-supervisor-53vtxjqd` and `pytest-of-Caetanogp123`, then confirm a clean tree.
2. Perform the formal baseline rollover for `9202567` and run the gate.
3. Execute one final Item 2 pilot with a bounded child timeout and verify no checkout artifacts.
4. Only after the pilot returns normally, launch the bounded long loop.

## Gotchas

- Retrieval, memory, and grounded generation are deferred to SPEC-008.
- Supervisor artifacts must remain outside the checkout.
- The live embedding adapter must never silently fall back to fake vectors.
- Do not delete `.handoff/.autonomous_gate_state.json`; use the formal rollover authorization.
- The last final-pilot attempt timed out without a structured response, but produced no new code;
  its two old checkout artifacts are cleanup-only residues.

## Resume

```powershell
git status --short --branch
git log -1 --oneline
python scripts/autonomous_gate.py
```

## Open questions

- None for the agreed SPEC-007 scope.
