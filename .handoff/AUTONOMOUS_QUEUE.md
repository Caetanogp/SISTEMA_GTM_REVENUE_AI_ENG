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

## Item 2 - Domain import state and loop test isolation

- **Scope:** `packages/core/revops/domain/`, `scripts/`, `tests/unit/domain/`, `tests/unit/scripts/`
- **What:** add pure import job/item state models, outcomes, and transitions; keep loop-created pytest artifacts out of mypy's source walk.
- **Done when:** state transition tests pass and the matching tasks.md checkbox is ticked.

## Item 3 - Ingestion outcomes and application contracts

- **Scope:** `packages/core/revops/domain/`, `packages/core/revops/application/`, `tests/unit/domain/`, `tests/unit/application/`, `tests/unit/scripts/`
- **Requires:** `packages/core/revops/domain/entities/ingestion.py`, `packages/core/revops/application/`, `tests/unit/domain/entities/test_ingestion.py`, `tests/unit/application/`
- **What:** split account/contact/enrichment outcomes, then add canonical ingestion DTOs, ports, and unit-tested use cases using the approved transaction design in `plan.md`.
- **Done when:** application tests prove staging, confirmation, grouping, idempotency, and partial results.

## Item 4 - Persistence and migration

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`, `tests/integration/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add ingestion/enrichment models, repositories, additive migration, and the authorized round-trip proof.
- **Done when:** repository integration tests and `upgrade -> downgrade -1 -> upgrade` pass.

## Item 5 - CSV and synthetic enrichment adapters

- **Scope:** `packages/core/revops/infrastructure/`, `tests/unit/infrastructure/`
- **Requires:** `packages/core/revops/infrastructure/`, `tests/unit/infrastructure/`
- **What:** parse bounded CSV input and add the schema-validated deterministic enrichment gateway.
- **Done when:** parser and provider unit tests pass.

## Item 6 - Celery worker and dispatcher

- **Scope:** `packages/core/revops/application/`, `packages/core/revops/infrastructure/`, `apps/worker/`, `tests/unit/`, `tests/integration/`
- **Requires:** `packages/core/revops/application/use_cases/ingestion.py`, `packages/core/revops/infrastructure/persistence/`, `packages/core/revops/infrastructure/queue/`, `apps/worker/`, `tests/unit/application/`, `tests/integration/`
- **What:** complete the approved per-domain processing contracts, persistence writes and enrichment FK, then add a minimal Redis/Celery dispatch path and idempotent worker composition root.
- **Done when:** duplicate delivery and broker failure behavior are tested.

## Item 7 - Administrative ingestion API

- **Scope:** `apps/api/`, `tests/unit/apps/`, `tests/integration/`
- **Requires:** `apps/api/`, `tests/integration/`
- **Closes:** 2 tasks.md checkboxes
- **What:** add admin-only JSON/CSV staging, confirmation, status, and paginated item routes.
- **Done when:** API integration tests cover the happy path and polling contract.

## Item 8 - Security and failure coverage

- **Scope:** `tests/adversarial/`, `tests/integration/`, `tests/unit/`
- **Requires:** `tests/adversarial/`, `tests/integration/`
- **What:** add malformed-input, authorization, PII-safe failure, queue failure, and tenant-isolation coverage.
- **Done when:** adversarial and failure-path tests pass.

## Item 9 - Documentation and closeout

- **Scope:** `README.md`, `docs/decisions/`, `docs/specs/SPEC-002-lead-account-ingestion/`, `.handoff/`
- **Requires:** `README.md`, `docs/decisions/`, `docs/specs/SPEC-002-lead-account-ingestion/`
- **Closes:** 3 tasks.md checkboxes
- **What:** record the queue/outbox ADR, setup documentation, acceptance evidence, and verified handoff.
- **Done when:** the final full gate is green and closeout checklist items are ticked.

## Rules for the loop

- Never use a worktree, push, merge, or touch `main`.
- Stop immediately at a genuine architecture decision not covered by `plan.md`.
- The user authorized the exact local migration sequence `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` for this SPEC-002 branch.
- This queue is limited to SPEC-002; it must not begin SPEC-003.
