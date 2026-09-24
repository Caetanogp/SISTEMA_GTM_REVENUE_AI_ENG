---
agent: codex
updated_at: 2026-09-24
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 Item 2 committed; Item 3 ready"
status: in_progress
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

Item 2 application contracts are implemented, tested, and committed. The next queue item is Item 3,
which covers infrastructure models and migrations. The pilot must not be relaunched until the gate
has been rerun from the committed Item 2 state.

## Done

- Item 2 implementation is present in `packages/core/revops/application/dto.py` and `ports.py`,
  with `tests/unit/application/test_knowledge_contracts.py`; `pytest tests/unit/application -q`
  passed (`70 passed`), and Ruff, format, mypy, and lint-imports passed on 2026-09-24. The executor
  reported this evidence before the session committed the change manually.
- Item 2 was committed as `feat(application): add knowledge ingestion contracts` after the executor
  lacked permission to create `.git/index.lock`.
- `c237b95` is the verified SPEC-006 integration head in `develop`.
- `0e73e66` moved supervisor temporary allocation outside the checkout and added preflight guards.
- `1adb120` removed child `TEMP/TMP/PYTEST_ADDOPTS` overrides; supervisor tests passed `28 tests`.
- `ab41212` corrected queue coverage counting so Item 1 closes two tasks.
- The residual pilot artifact was confirmed absent with `Test-Path=False` on 2026-09-20.
- Domain/chunking pilot implementation is present in `packages/core/revops/domain/entities/knowledge.py`;
  Ruff, format, mypy, lint-imports, and domain/architecture tests passed (`128 passed`).
- Supervisor and launcher regression suites passed (`30 passed`); the native executable resolution
  fix passed its focused launcher tests (`2 passed`) and was committed as `d60b770`.
- The supervisor baseline was formally rolled over to `d60b770`; the gate reports Item 2 green but
  not yet ticked in `tasks.md`.
- The native Codex binary is installed and responds to `--version` as `codex-cli 0.150.0`.

## Next

1. Run `python scripts/autonomous_gate.py` after the Item 2 commit and retain its exit code/output.
2. Confirm the gate advances its baseline to the committed Item 2 state without a scope violation.
3. Only then resume Item 3; do not relaunch the old pilot against the already-completed Item 2.

## Gotchas

- Retrieval, memory, and grounded generation are deferred to SPEC-008.
- Supervisor artifacts must remain outside the checkout.
- The live embedding adapter must never silently fall back to fake vectors.
- Do not delete `.handoff/.autonomous_gate_state.json`; use the formal rollover authorization.
- The native executable is not exposed as `codex.exe` on PATH; the launcher resolves it from the
  installed package instead of falling back to `codex.cmd`.
- The latest final-pilot attempt did not return within the configured 120-second child timeout;
  no checkout artifacts or code changes were produced. Do not launch the long loop yet.
- A follow-up pilot with a 600-second child timeout was started but intentionally interrupted
  before it produced a result; it left no running supervisor child, checkout artifacts, or code
  changes.
- In the subsequent uninterrupted attempt, the native Codex child exited but the supervisor
  process did not return its structured result or final status. The pilot was then interrupted
  after confirming that only the pilot supervisor was stopped. This is now a concrete runner
  lifecycle/pipe-handling blocker; do not launch the long loop until it is fixed and tested.

## Resume

```powershell
git status --short --branch
git log -1 --oneline
python scripts/autonomous_gate.py
```

## Open questions

- None for the agreed SPEC-007 scope.
