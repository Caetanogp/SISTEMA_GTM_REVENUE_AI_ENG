# Autonomous work queue

The only source of work for an unattended loop session. Work items run in order, stay inside their
declared scope, and tick the mapped active-spec checklist item only after their own files are
committed. `scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-002-lead-account-ingestion/tasks.md`

## Item 1 - Autonomous gate and queue setup

- **Scope:** `scripts/`, `.handoff/`, `tests/unit/scripts/`
- **Closes:** 2 tasks.md checkboxes
- **What:** generalize the gate and activate the scoped SPEC-002 queue.
- **Done when:** gate tests pass and both matching tasks.md checkboxes are ticked.

## Item 2 - Application contracts

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **What:** add canonical ingestion DTOs, ports, and unit-tested use cases.
- **Done when:** application tests prove staging, confirmation, grouping, idempotency, and partial results.

## Item 3 - Persistence and migration

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add ingestion/enrichment models, repositories, additive migration, and the authorized round-trip proof.
- **Done when:** repository integration tests and `upgrade -> downgrade -1 -> upgrade` pass.

## Item 4 - CSV and synthetic enrichment adapters

- **Scope:** `packages/core/revops/infrastructure/`, `tests/unit/infrastructure/`
- **What:** parse bounded CSV input and add the schema-validated deterministic enrichment gateway.
- **Done when:** parser and provider unit tests pass.

## Item 5 - Celery worker and dispatcher

- **Scope:** `packages/core/revops/infrastructure/queue/`, `apps/worker/`, `tests/unit/`, `tests/integration/`
- **What:** add a minimal Redis/Celery dispatch path and idempotent worker composition root.
- **Done when:** duplicate delivery and broker failure behavior are tested.

## Item 6 - Administrative ingestion API

- **Scope:** `apps/api/`, `tests/unit/apps/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add admin-only JSON/CSV staging, confirmation, status, and paginated item routes.
- **Done when:** API integration tests cover the happy path and polling contract.

## Item 7 - Security and failure coverage

- **Scope:** `tests/adversarial/`, `tests/integration/`, `tests/unit/`
- **What:** add malformed-input, authorization, PII-safe failure, queue failure, and tenant-isolation coverage.
- **Done when:** adversarial and failure-path tests pass.

## Item 8 - Documentation and closeout

- **Scope:** `README.md`, `docs/decisions/`, `docs/specs/SPEC-002-lead-account-ingestion/`, `.handoff/`
- **Closes:** 3 tasks.md checkboxes
- **What:** record the queue/outbox ADR, setup documentation, acceptance evidence, and verified handoff.
- **Done when:** the final full gate is green and closeout checklist items are ticked.

## Rules for the loop

- Never use a worktree, push, merge, or touch `main`.
- Stop immediately at a genuine architecture decision not covered by `plan.md`.
- The user authorized the exact local migration sequence `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` for this SPEC-002 branch.
- This queue is limited to SPEC-002; it must not begin SPEC-003.
