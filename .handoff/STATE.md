---
agent: codex
updated_at: 2026-09-24
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 native Codex pilot blocked"
status: in_progress
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

SPEC-005 and SPEC-006 are merged into `develop` and published to `origin/develop`.
SPEC-007 documentation and queue are materialized on `feature/SPEC-007-rag-ingestion`.
The domain/chunking implementation and tests are complete. The supervisor and launcher preserve
native Windows temp variables, remove only the custom pytest override, bound child execution time,
and keep supervisor artifacts outside the checkout. The launcher now resolves the bundled native
Codex executable when it is not on PATH. The native executable pilot started but did not return a
structured response within the bounded run; it was interrupted. The checkout remained clean and
no supervisor or pytest artifacts were recreated.

## Done

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

1. Diagnose why the native Codex child does not return a structured response under the supervisor,
   using read-only process and command-line checks.
2. Repeat the bounded pilot only after the cause is understood; require normal return and no
   checkout artifacts.
3. Tick Item 2 only when the executor has produced the required application-layer implementation
   and evidence, then run the gate.
4. Only after the pilot and gate pass, launch the bounded long loop.

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

## Autonomous loop HALT (2026-09-24T05:03:04+00:00)

The pipe-handling fix allowed the supervisor to receive the executor's structured response, but the
executor could not complete mandatory terminal checks (`git rev-parse`, `AGENTS.md` read, and a
minimal echo) and timed out after 600 seconds. No repository files were changed. Do not launch the
long loop until the executor terminal environment is responsive and a bounded pilot completes.
