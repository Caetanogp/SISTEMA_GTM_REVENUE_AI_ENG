# Autonomous work queue

This queue is the only source of unattended work for the approved SPEC-011 implementation. Items
run in order, each item closes exactly one checkbox in `docs/specs/SPEC-011-reply-intelligence/tasks.md`,
and `scripts/autonomous_gate.py` is the completion judge.

- **Tasks file:** `docs/specs/SPEC-011-reply-intelligence/tasks.md`

## Item 1 - Reply domain policy
- **Scope:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Requires:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Closes:** 1 tasks.md checkbox
- **What:** implement immutable reply values, nine categories, the approved category-to-action mapping, confidence threshold `0.80`, bilingual policy, evidence boundaries, and unsubscribe precedence.
- **Done when:** focused domain tests pass, the item commit is created by the supervisor, and the gate advances.

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
- **Scope:** `packages/core/revops/infrastructure/agent/`, `infrastructure/agent/prompts/`, `tests/unit/infrastructure/agent/`
- **Requires:** `packages/core/revops/infrastructure/agent/`, `infrastructure/agent/prompts/`, `tests/unit/infrastructure/agent/`
- **Closes:** 1 tasks.md checkbox
- **What:** add versioned structured prompt, allowlisted low-risk tool, dedicated graph lifecycle, bounded artifact, and usage journal.
- **Done when:** graph lifecycle, schema, prompt, and no-side-effect tests pass.

## Item 5 - API and artifact reader
- **Scope:** `apps/api/`, `tests/integration/`, `packages/core/revops/application/`
- **Requires:** `apps/api/`, `tests/integration/`, `packages/core/revops/application/`
- **Closes:** 1 tasks.md checkbox
- **What:** expose reply registration, classify, typed result, and immutable feedback endpoints with authenticated organization scope.
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
- **Scope:** `docs/requirements/`, `docs/security/`, `.handoff/`, `docs/specs/SPEC-011-reply-intelligence/`
- **Requires:** `docs/requirements/`, `docs/security/`, `.handoff/`, `docs/specs/SPEC-011-reply-intelligence/`
- **Closes:** 1 tasks.md checkbox
- **What:** record PDF file:line evidence, security review, final verification output, and handoff closeout.
- **Done when:** full verification, eval gate, traceability checker, security checks, and clean-tree checks pass.

## Loop rules

- Executors cannot edit this queue, supervisor controls, gate, `AGENTS.md`, or `CLAUDE.md`.
- Return `architecture_required` for an uncovered reversible technical shape; return `HUMAN_REQUIRED` for product, security, dependency, destructive, external-action, or non-dominant decisions.
- No push, merge, main/develop work, skipped tests, weakened checks, or checkout temp artifacts.
- Commit one logical item before the gate checks task evidence. The supervisor owns commits.
