---
agent: codex
updated_at: 2026-09-24T20:01:38-03:00
branch: feature/SPEC-007-rag-ingestion
spec: SPEC-007-rag-ingestion
phase: "SPEC-007 Item 3 architecture decision required"
status: architecture_required
---

# Current state

## Goal

Implement the PDF-aligned, versioned, tenant-scoped knowledge ingestion pipeline with pgvector,
immutable publication history, bounded embeddings, and an offline contract evaluation.

## Now

Item 3 is blocked before implementation. The approved spec requires shared platform content and
organization-private content, but does not resolve the database ownership/corpus-head representation
for platform content. The existing `KnowledgeDocumentVersion` contract has a non-null
`organization_id`, so a sentinel organization and a nullable organization ID are both defensible
but materially different persistence designs.

## Done

- Item 2 implementation is present in `packages/core/revops/application/dto.py` and `ports.py`,
  with `tests/unit/application/test_knowledge_contracts.py`; `pytest tests/unit/application -q`
  passed (`70 passed`), and Ruff, format, mypy, and lint-imports passed on 2026-09-24. The executor
  reported this evidence before the session committed the change manually.
- Item 2 was committed as `feat(application): add knowledge ingestion contracts` after the executor
  lacked permission to create `.git/index.lock`.
- `python scripts/autonomous_gate.py` was rerun on 2026-09-24 from the committed Item 2 checkout;
  Item 3 was reported as gate-green with Ruff, mypy, lint-imports, pytest, and `check_agent_docs`
  all passing.
- `22619a1` grants implementation children only the checkout `.git` directory through Codex
  `--add-dir`, preserving the workspace sandbox and allowing executor-created commits.
- `c237b95` is the verified SPEC-006 integration head in `develop`.
- `0e73e66` moved supervisor temporary allocation outside the checkout and added preflight guards.
- `1adb120` removed child `TEMP/TMP/PYTEST_ADDOPTS` overrides; supervisor tests passed `28 tests`.
- `ab41212` corrected queue coverage counting so Item 1 closes two tasks.
- The residual pilot artifact was confirmed absent with `Test-Path=False` on 2026-09-20.
- Domain/chunking pilot implementation is present in `packages/core/revops/domain/entities/knowledge.py`;
  Ruff, format, mypy, lint-imports, and domain/architecture tests passed (`128 passed`).
- Supervisor and launcher regression suites passed (`30 passed`); the native executable resolution
  fix passed its focused launcher tests (`2 passed`) and was committed as `d60b770`.
- The supervisor baseline was formally rolled over through `65d9883`; Item 3 is the active gated
  item and its architecture decision is currently required.
- The native Codex binary is installed and responds to `--version` as `codex-cli 0.150.0`.

## Next

1. Resolve the platform-content ownership and corpus-head model in SPEC-007 documentation.
2. Reconcile the application contracts if that decision changes their non-null organization scope.
3. Implement only Item 3 models, migration, and migration/model tests after approval.

## Gotchas

- Retrieval, memory, and grounded generation are deferred to SPEC-008.
- Supervisor artifacts must remain outside the checkout.
- The live embedding adapter must never silently fall back to fake vectors.
- Do not delete `.handoff/.autonomous_gate_state.json`; use the formal rollover authorization.
- The native executable is not exposed as `codex.exe` on PATH; the launcher resolves it from the
  installed package instead of falling back to `codex.cmd`.
- `KnowledgeDocumentVersion` and the current knowledge repository ports take a non-null
  organization UUID, while the spec also requires platform-scoped seed content. Do not choose a
  sentinel organization or nullable tenant FK without an approved architecture decision.
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
Get-Content -Raw docs/specs/SPEC-007-rag-ingestion/spec.md
Get-Content -Raw docs/specs/SPEC-007-rag-ingestion/plan.md
```

## Open questions

- How must platform-scoped knowledge be owned and addressed in persistence: a dedicated immutable
  platform corpus identity, or nullable organization ownership with explicit scope constraints?

## Autonomous loop HALT (2026-09-24T23:02:08+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. Architecture escalation was requested after uncommitted changes; refusing to design over a partial implementation

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
