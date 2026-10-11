---
agent: codex
updated_at: 2026-10-12
branch: feature/SPEC-011-reply-intelligence
spec: SPEC-011-reply-intelligence
phase: "Item 7 adversarial and restart regression implemented; ready for supervisor gate"
status: in_progress
---

# Current state

## Goal

Implement bounded bilingual reply classification, recommended next actions, immutable feedback, and offline evidence without adding external writes or changing existing runtimes.

## Now

Items 1-7 are implemented and verified locally. Item 7 awaits the supervisor commit and gate;
do not run the autonomous gate from this dirty executor worktree.

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
- Item 5 contract approved: `POST/GET /replies`, `POST /replies/{reply_id}/classify`, existing
  `GET /agent/runs/{run_id}/result`, feedback `POST/GET`, header `Idempotency-Key`, and explicit
  `in_progress`/`completed`/`failed`/`recovery_required` response states, recorded in plan/ADR.
- Item 5 adds authenticated reply registration/read/classification/feedback endpoints and composes
  only the bounded reply runtime. `ReplyArtifactReader` reads completed typed artifacts directly
  from the checkpoint store; the existing result route dispatches reply runs before constructing
  legacy graph, provider, or RAG components. Embeddings are lazy so reply-only requests do not
  initialize a provider. `tests/integration/test_reply_api.py` proves the terminal read makes no
  second gateway call, including when a live embedding provider is intentionally unconfigured.
- Observed Item 5 evidence: `ruff check apps/api packages/core/revops/infrastructure/agent/reply_runtime.py tests/integration/test_reply_api.py`, format check, and `mypy apps/api packages/core/revops/infrastructure/agent/reply_runtime.py` passed; focused integration command passed 8 tests; `lint-imports` kept all 4 contracts; `git diff --check` passed.
- Item 6 adds 90 synthetic bilingual examples (five per category/language), a deterministic
  independent lexical baseline, five policy-contract cases, and multi-metric gate support. The
  gate enforces baseline accuracy >= 0.85, macro-F1 >= 0.80, unsubscribe recall = 1.00, and the
  reply classification contract at 1.00; `docs/evals/reply-classification.md` records the scope.
- Observed Item 6 evidence: `ruff check evals tests/unit/evals`, `ruff format --check evals tests/unit/evals docs/evals`, `mypy evals`, focused `pytest tests/unit/evals/test_reply_classification_scorer.py tests/unit/evals/test_gate.py -q` (10 passed), `python -m evals.gate` (all suites passed; reply contract 5/5; baseline 90/90 and all three metrics 1.00), and `git diff --check` passed. The complete eval unit suite reached 39 passed but its pre-existing `tmp_path` test cannot create its sandbox temporary directory.
- Item 7 adds `tests/adversarial/test_reply_intelligence_security.py` for injection/PII fencing and fake-evidence manual review, extends `tests/integration/test_reply_api.py` with cross-tenant authorization and a real PostgreSQL checkpoint restart that makes no second provider call, and corrects migration-history regressions to the approved reply-migration head `c4d5e6f7a8b9`.
- Observed Item 7 evidence: `ruff check tests/adversarial tests/integration tests/unit` and `ruff format --check tests/adversarial tests/integration tests/unit` passed (121 files); targeted `mypy` passed (4 files); `pytest tests/adversarial -q` passed (32); `pytest tests/integration -q` passed (52); `lint-imports` kept all 4 contracts; `git diff --check` passed. `pytest tests/unit -q` reached 455 passed but has 50 pre-existing `tmp_path` setup errors because the sandbox denies the user temp directory.

## Next

1. Supervisor: validate the Item 7 diff, commit it, and run the autonomous gate from the clean parent process.
2. Continue only with Item 8 if the gate advances.
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

## Autonomous loop HALT (2026-10-11T23:03:15+00:00)

HUMAN_REQUIRED: autonomous architecture supervisor stopped. A implementação exigiria inventar um contrato público de API; pelas instruções, isso requer decisão humana antes de editar qualquer arquivo.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-10-11T23:10:08+00:00)

Item 5 declares scope ('apps/api/', 'tests/integration/', 'packages/core/revops/application/', 'packages/core/revops/infrastructure/agent/', 'packages/core/revops/infrastructure/persistence/'), but changes touch files outside it: ['docs/decisions/ADR-0019-reply-intelligence-runtime.md', 'docs/specs/SPEC-011-reply-intelligence/plan.md']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
