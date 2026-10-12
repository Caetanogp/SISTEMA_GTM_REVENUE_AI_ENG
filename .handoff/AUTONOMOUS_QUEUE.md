# Autonomous work queue

This queue is the only source of unattended work for the approved SPEC-011 implementation. Items
run in order, each item closes exactly one checkbox in `docs/specs/SPEC-011-reply-intelligence/tasks.md`,
and `scripts/autonomous_gate.py` is the completion judge.

- **Tasks file:** `docs/specs/SPEC-011-reply-intelligence/tasks.md`

## Item 1 - Reply domain policy
- **Scope:** `packages/core/revops/domain/`, `tests/unit/domain/`, `docs/specs/SPEC-011-reply-intelligence/`, `docs/decisions/ADR-0019-reply-intelligence-runtime.md`, `.handoff/AUTONOMOUS_QUEUE.md`, `scripts/codex_loop_supervisor.py`, `tests/unit/scripts/test_codex_loop_supervisor.py`
- **Requires:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Closes:** 1 tasks.md checkbox
- **What:** implement immutable reply values, nine categories, the approved category-to-action mapping, confidence threshold `0.80`, bilingual policy, evidence boundaries, and unsubscribe precedence.
- **Done when:** focused domain tests pass, the item commit is created by the supervisor, and the gate advances.

The supervisor paths above are bootstrap-only changes already reviewed and committed before the
pilot; executors remain prohibited from editing supervisor controls.

## Item 2 - Application contracts
- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** `packages/core/revops/application/`, `tests/unit/application/`
- **Closes:** 1 tasks.md checkbox
- **What:** add DTOs, ports, use cases, canonical tenant/contact validation, and feedback semantics.
- **Done when:** application unit tests and mypy pass with no framework imports in inner layers.

## Item 3 - Persistence and idempotency
- **Scope:** `packages/core/revops/infrastructure/persistence/`, `alembic/`, `tests/integration/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`, `alembic/`, `tests/integration/`
- **Closes:** 1 tasks.md checkbox
- **What:** add additive reply tables, repositories, atomic reservation, replay rules, and feedback history.
- **Done when:** PostgreSQL migration and concurrency/idempotency tests pass without changing prior data.

## Item 4 - Prompt, tool, and graph
- **Scope:** `packages/core/revops/domain/`, `packages/core/revops/application/`, `packages/core/revops/infrastructure/agent/`, `packages/core/revops/infrastructure/persistence/`, `tests/unit/domain/`, `tests/unit/application/`, `tests/unit/infrastructure/agent/`, `tests/unit/evals/`, `tests/integration/`, `evals/`
- **Requires:** `packages/core/revops/domain/values/reply.py`, `packages/core/revops/application/dto.py`, `packages/core/revops/application/ports.py`, `packages/core/revops/application/use_cases/reply.py`, `packages/core/revops/infrastructure/agent/`, `packages/core/revops/infrastructure/agent/prompts/classify_reply.v1.md`, `packages/core/revops/infrastructure/persistence/`, `tests/unit/domain/values/test_reply.py`, `tests/unit/application/use_cases/test_reply.py`, `tests/unit/infrastructure/agent/`, `tests/unit/evals/`, `tests/integration/`, `evals/`
- **Closes:** 1 tasks.md checkbox
- **What:** add the versioned structured prompt, allowlisted low-risk tool, dedicated checkpointed graph lifecycle, bounded typed artifact, same-connection advisory lock, restart-safe replay, and usage journal. Keep existing v1/v2 compositions unchanged; add the minimum offline runtime-contract eval.
- **Done when:** graph lifecycle, schema, prompt, and no-side-effect tests pass.

## Item 5 - API and artifact reader
- **Scope:** `apps/api/`, `tests/integration/`, `packages/core/revops/application/`, `packages/core/revops/infrastructure/agent/`, `packages/core/revops/infrastructure/persistence/`
- **Requires:** `apps/api/`, `tests/integration/`, `packages/core/revops/application/`, `packages/core/revops/infrastructure/agent/`, `packages/core/revops/infrastructure/persistence/`
- **Closes:** 1 tasks.md checkbox
- **What:** expose reply registration, classify, typed result, and immutable feedback endpoints with authenticated organization scope.
- **What:** expose reply registration, classify, typed result, and immutable feedback endpoints with authenticated organization scope. Read terminal artifacts through the direct checkpoint/artifact reader without constructing a graph or initializing provider/RAG components.
- **Done when:** API integration tests pass and terminal reads do not initialize graph/provider/RAG components.

## Item 6 - Dataset and eval gates
- **Scope:** `evals/`, `tests/unit/evals/`, `docs/evals/`
- **Requires:** `evals/`, `tests/unit/evals/`, `docs/evals/`
- **Closes:** 1 tasks.md checkbox
- **What:** add 90 synthetic bilingual cases, independent deterministic baseline metrics, contract scorer, and additive thresholds.
- **Done when:** contract is 1.00, accuracy is at least .85, macro-F1 at least .80, and unsubscribe recall is 1.00.

## Item 7 - Adversarial and restart regression
- **Scope:** `tests/adversarial/`, `tests/integration/`, `tests/unit/`
- **Requires:** `tests/adversarial/`, `tests/integration/`, `tests/unit/`
- **Closes:** 1 tasks.md checkbox
- **What:** cover injection, PII, authorization, fake evidence, concurrency, process restart, and existing runtime compatibility.
- **Done when:** focused and regression suites pass with no skipped or weakened checks.

## Item 8 - Traceability and verification
- **Scope:** `docs/requirements/`, `docs/security/`, `.handoff/`, `docs/specs/SPEC-011-reply-intelligence/`, `packages/core/revops/application/ports.py`, `packages/core/revops/application/use_cases/ingestion.py`, `tests/unit/application/use_cases/test_reply.py`, `tests/unit/application/use_cases/test_ingestion.py`, `tests/integration/test_reply_persistence.py`, `requirements-ci.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/evals.yml`
- **Requires:** `docs/requirements/`, `docs/security/`, `.handoff/`, `docs/specs/SPEC-011-reply-intelligence/`, `packages/core/revops/application/ports.py`, `packages/core/revops/application/use_cases/ingestion.py`, `tests/unit/application/use_cases/test_reply.py`, `tests/unit/application/use_cases/test_ingestion.py`, `tests/integration/test_reply_persistence.py`, `requirements-ci.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/evals.yml`
- **Closes:** 1 tasks.md checkbox
- **What:** record PDF file:line evidence; replace the four ingestion B101 assertions with explicit invariant checks; establish an exact-version Python 3.12 Linux CI dependency input; run Semgrep, Bandit, dependency audit, full verification, and handoff closeout.
- **Done when:** full verification, eval gate, traceability checker, Semgrep, Bandit, `pip-audit --strict --no-deps -r requirements-ci.txt`, and clean-tree checks pass without suppressions or weakened thresholds.

## Loop rules

- Executors cannot edit this queue, supervisor controls, gate, `AGENTS.md`, or `CLAUDE.md`.
- Return `architecture_required` for an uncovered reversible technical shape; return `HUMAN_REQUIRED` for product, security, dependency, destructive, external-action, or non-dominant decisions.
- No push, merge, main/develop work, skipped tests, weakened checks, or checkout temp artifacts.
- Commit one logical item before the gate checks task evidence. The supervisor owns commits.
