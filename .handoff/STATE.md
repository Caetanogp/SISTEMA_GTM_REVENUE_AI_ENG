---
agent: codex
updated_at: 2026-10-11
branch: feature/SPEC-011-reply-intelligence
spec: SPEC-011-reply-intelligence
phase: "Item 4 verified; Item 5 is next"
status: in_progress
---

# Current state

## Goal

Implement bounded bilingual reply classification, recommended next actions, immutable feedback, and offline evidence without adding external writes or changing existing runtimes.

## Now

Items 1-4 are implemented and verified. The clean feature branch is ready for the unattended
supervisor to implement Item 5 (authenticated reply APIs and direct artifact reads).

## Done

- Reply policy is implemented in `packages/core/revops/domain/values/reply.py`; it contains the nine-category mapping, finite `[0, 1]` confidence validation, inclusive `0.80` threshold, `en`/`pt` language compatibility, bounded half-open evidence offsets, conservative opt-out precedence, and manual-review fallback.
- Focused contract coverage is in `tests/unit/domain/values/test_reply.py`; `pytest tests/unit/domain -q` passed (193 passed), `ruff check packages/core/revops/domain tests/unit/domain` passed, `ruff format --check packages/core/revops/domain tests/unit/domain` passed, `mypy packages/core/revops/domain` passed, and `lint-imports` kept all 4 contracts.
- The first SPEC-011 checkbox is ticked in `docs/specs/SPEC-011-reply-intelligence/tasks.md` after observed evidence. Pilot commit `a3f954c` is on the feature branch and the gate advanced to Item 2.
- Reply application contracts now include tenant-injected registration DTOs, strict structured classification output, immutable reply/request/feedback records and ports, a reply-specific unit of work, canonical account/contact validation, one-run reservation with its started event, and append-only idempotent feedback use cases. The run journal contains only a reply identifier, never reply text.
- `tests/unit/application/use_cases/test_reply.py` covers canonical alias replay, relationship rejection, single reservation, no raw-reply run metadata, tenant-scoped append-only feedback, idempotency conflict, DTO boundary validation, and the structural reply UoW port.
- Observed verification for Item 2: `ruff check packages/core/revops/application tests/unit/application` passed; `ruff format --check packages/core/revops/application tests/unit/application` passed; `mypy packages/core/revops/application` passed; `pytest tests/unit/application -q` passed (105 passed, with only the known restricted `.pytest_cache` warning); `lint-imports` kept all 4 contracts; `git diff --check` passed.
- Item 3 adds the additive `replies`, `reply_classification_requests`, and `reply_feedback`
  SQLAlchemy models, migration `c4d5e6f7a8b9`, reply-specific repositories/unit of work, tenant-scoped
  foreign keys and idempotency constraints, plus PostgreSQL concurrency coverage in
  `tests/integration/test_reply_persistence.py`. Transactional advisory locks serialize the existing
  read-then-create contracts for reply registration, classification reservation, and feedback replay.
- Observed non-PostgreSQL verification for Item 3: `ruff check packages/core/revops/infrastructure/persistence tests/integration/test_reply_persistence.py` passed; `ruff format --check packages/core/revops/infrastructure/persistence tests/integration/test_reply_persistence.py` passed (28 files); `python -m py_compile` passed for all changed Python files; `lint-imports` kept all 4 contracts; `git diff --check` passed; the focused test collected one integration test.
- Item 3 verification was subsequently completed after Docker became available: `docker compose up -d` started healthy PostgreSQL/Redis; migration `c4d5e6f7a8b9` applied; `pytest tests/integration/test_reply_persistence.py -q` -> 1 passed; Ruff, format check, mypy, and `git diff --check` passed. The reservation order was corrected to persist the run and started event before its FK-backed classification request.
- Approved Item 4 architecture is recorded in `docs/specs/SPEC-011-reply-intelligence/plan.md` and `docs/decisions/ADR-0019-reply-intelligence-runtime.md`; the queue requires the real package prompt path and the Item 4 cross-layer/runtime evidence.
- Item 4 now adds `reply_runtime.py`: fixed `select`/`reserve`/`execute`/`complete` lifecycle,
  a canonical compact 128 KiB typed artifact, 30-second runtime/20-second inference bounds,
  durable synchronous checkpoints, fail-closed reserved-state recovery, and deterministic terminal
  event reconciliation. `locked_reply_checkpointer` obtains a non-blocking organization/run
  PostgreSQL advisory lock and constructs `AsyncPostgresSaver` on that exact connection.
- `tests/unit/infrastructure/agent/test_reply_runtime.py` covers lifecycle artifact sanitization,
  Unicode prompt preservation/delimiter rejection, and usage-only terminal journal metadata.
  `tests/integration/test_reply_runtime_lock.py` passed against PostgreSQL, proving concurrent
  acquisition returns `in_progress` and the lock releases correctly. The new
  `reply_runtime_contract` offline suite passed 4/4 and is mandatory in `evals.gate`.
- Observed final Item 4 evidence: `ruff check` and format check passed for all touched runtime,
  persistence, eval, unit, and integration paths; `mypy` passed (50 source files); focused pytest
  passed (54 passed); `python -m evals.gate` passed all nine suites; `lint-imports` kept all four
  contracts; `git diff --check` passed. The fourth SPEC-011 checkbox is ticked.

## Next

1. Launch the real long loop from the clean feature branch with `MaxTurns 100` for Items 5-8.
2. Attach the external watcher to the new supervisor PID and stdout log.
3. Stop on `GOAL ACHIEVED`, `architecture_required`, `HUMAN_REQUIRED`, or a deterministic gate failure.

## Gotchas

- The authoritative checkout is `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`; the OneDrive checkout is stale and must not be used.
- Set `PYTHONPATH` to `packages\\core;repo-root` before Python checks to avoid stale editable imports.
- Do not delete or reset `.handoff/.autonomous_gate_state.json`; the gate reboots its baseline when the task count changes.
- The queue uses exact required paths so the gate can reject false task completion.
- Pytest reports a non-fatal warning because the restricted sandbox cannot update `.pytest_cache`; test execution itself passed.
- Docker must remain running while integration items execute; current Docker services are healthy.

## Resume

```powershell
Set-Location -LiteralPath "C:\Dev\SISTEMA_PORTFOLIO_AI_ENG"
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

## Open questions

None for the approved SPEC-011 scope. A newly discovered product or security choice must stop the queue and be brought back for deliberate design.

## Autonomous loop HALT (2026-10-10T21:55:41+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. A reachable PostgreSQL service is required to run the mandatory migration and concurrency/idempotency evidence. Making that external service available requires human action in this sandbox.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-10-10T22:40:39+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. Architecture plan was not approved after 2 attempts

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-10-11T22:59:01+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. Executor changes outside Item 4 scope cannot be committed: ['tests/unit/evals/test_gate.py']

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
