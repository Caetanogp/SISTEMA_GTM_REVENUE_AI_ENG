# Autonomous work queue

The only source of work for an unattended loop session. Work items run in order, stay inside their
declared scope, and tick the mapped SPEC-003 checklist item only after their own files are committed.
`scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-003-deduplication/tasks.md`

## Item 1 - Specification and queue activation

- **Scope:** `.handoff/`, `docs/specs/`, `scripts/`
- **Closes:** 2 tasks.md checkboxes
- **What:** commit the approved SPEC-003 documents, update the roadmap and handoff, activate this
  scoped queue, and prove the pilot gate behavior.
- **Done when:** the three documents are present, queue metadata selects SPEC-003, and the gate
  accepts the queue without a scope violation.

## Item 2 - Domain normalization and matching policy

- **Scope:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Requires:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add E.164 phone validation, deterministic text keys, matching reasons/scores,
  fingerprints, and scan/candidate/alias state invariants.
- **Done when:** pure domain tests cover every policy boundary and the pilot passes.

## Item 3 - Deduplication application contracts

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** `packages/core/revops/application/`, `tests/unit/application/`
- **Closes:** 2 tasks.md checkboxes
- **What:** define DTOs and ports, canonical resolution, and scan/list/dismiss/merge/revert use
  cases behind a dedicated unit of work.
- **Done when:** unit tests prove tenant isolation, idempotency, suppression, stale candidates,
  master selection, alias invariants, and reversible decisions.

## Item 4 - Persistence and migration

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`, `tests/integration/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`, `tests/integration/`
- **Closes:** 3 tasks.md checkboxes
- **What:** add phone, scan, candidate, typed alias, event models and repositories with additive
  migration and concrete tenant-scoped foreign keys.
- **Done when:** repository tests and the authorized migration round-trip pass.

## Item 5 - Ingestion and canonical write compatibility

- **Scope:** `packages/core/revops/application/`, `packages/core/revops/infrastructure/ingestion/`, `apps/api/`, `tests/unit/`, `tests/integration/`
- **Requires:** `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** accept optional E.164 phone in JSON/CSV, resolve existing aliases for ingestion, and
  aggregate canonical account reads and account-bound writes.
- **Done when:** backward-compatible ingestion and canonicalization integration tests pass.

## Item 6 - Asynchronous scan worker

- **Scope:** `packages/core/revops/infrastructure/queue/`, `apps/worker/`, `tests/unit/`, `tests/integration/`
- **Requires:** `apps/worker/`, `tests/integration/`
- **Closes:** 1 tasks.md checkbox
- **What:** publish and process bounded tenant scans through Celery with retries, idempotent
  candidate upserts, queue-failure visibility, and duplicate-delivery safety.
- **Done when:** a real Redis/Celery integration test proves scan completion and replay behavior.

## Item 7 - Administrative deduplication API

- **Scope:** `apps/api/`, `tests/unit/apps/`, `tests/integration/`
- **Requires:** `apps/api/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add admin-only scan, status, candidate pagination, dismissal, merge, history, and
  revert routes with idempotency and HTTP error contracts.
- **Done when:** integration tests cover authorization, pagination, replay, stale decisions, and
  the full review-to-revert flow.

## Item 8 - Security, concurrency, and failure coverage

- **Scope:** `tests/adversarial/`, `tests/integration/`, `tests/unit/`
- **Requires:** `tests/adversarial/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** prove tenant isolation, PII-safe events, input bounds, concurrent decisions, broker
  failure, worker retry, and candidate explosion protection.
- **Done when:** adversarial and integration failure-path suites pass without weakening checks.

## Item 9 - Documentation and closeout

- **Scope:** `README.md`, `docs/decisions/`, `docs/specs/SPEC-003-deduplication/`, `.handoff/`
- **Requires:** `README.md`, `docs/decisions/`, `docs/specs/SPEC-003-deduplication/`
- **Closes:** 2 tasks.md checkboxes
- **What:** record the logical-alias ADR, setup and operation docs, acceptance evidence, and final
  handoff.
- **Done when:** every acceptance criterion maps to observed evidence and the full gate is green.

## Rules for the loop

- Never use a worktree, push, merge, or touch `main`.
- Stop immediately at a genuine architecture decision not covered by SPEC-003 `plan.md`.
- The queue is limited to SPEC-003 and must not begin SPEC-004.
- Every item's own implementation files must be committed before its checklist boxes are ticked.
