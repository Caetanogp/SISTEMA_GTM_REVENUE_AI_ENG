---
agent: codex
updated_at: 2026-09-20
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 pilot ready to rerun"
status: in_progress
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

SPEC-005 and SPEC-006 are merged into `develop` and published to `origin/develop`.
SPEC-007 documentation and queue are materialized on `feature/SPEC-007-rag-ingestion`.
The first pilot exposed a Windows child-temp-path regression; the generated checkout artifact was
removed, and the supervisor fix is committed and ready for a clean pilot rerun.

## Done

- `c237b95` is the verified SPEC-006 integration head in `develop`.
- `0e73e66` moved supervisor temporary allocation outside the checkout and added preflight guards.
- `1adb120` removed child `TEMP/TMP/PYTEST_ADDOPTS` overrides; supervisor tests passed `28 tests`.
- `ab41212` corrected queue coverage counting so Item 1 closes two tasks.
- The residual pilot artifact was confirmed absent with `Test-Path=False` on 2026-09-20.

## Next

1. Commit this reconciled handoff and restore the cleanup helper to its baseline content.
2. Perform the formal external baseline rollover for the authorized supervisor/control commits.
3. Rerun the short Item 1 domain/chunking pilot and verify no checkout temp artifact appears.
4. After a green pilot and gate, launch the bounded long loop for remaining SPEC-007 items.

## Gotchas

- Retrieval, memory, and grounded generation are deferred to SPEC-008.
- Supervisor artifacts must remain outside the checkout.
- The live embedding adapter must never silently fall back to fake vectors.
- Do not delete `.handoff/.autonomous_gate_state.json`; use the formal rollover authorization.

## Resume

```powershell
git status --short --branch
git log -1 --oneline
python scripts/autonomous_gate.py
```

## Open questions

- None for the agreed SPEC-007 scope.
