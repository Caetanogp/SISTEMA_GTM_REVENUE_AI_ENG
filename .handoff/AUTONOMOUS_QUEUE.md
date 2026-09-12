# Autonomous work queue

The only source of work for the SPEC-005 unattended loop. Items run in order and remain inside
their declared file scope. `scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-005-crm-attribution-model/tasks.md`

## Item 1 - Domain attribution contracts

- **Scope:** `packages/core/revops/domain/`, `tests/unit/domain/`, `.gitignore`
- **Requires:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Closes:** 1 tasks.md checkbox
- **What:** define pure Campaign, Touchpoint and opportunity-status contracts.
- **Done when:** domain unit tests cover valid values, invalid status, timestamps and invariants.

## Item 2 - Application ports and DTOs

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** `packages/core/revops/application/`, `tests/unit/application/`
- **Closes:** 1 tasks.md checkbox
- **What:** define tenant-scoped attribution DTOs and repository ports with strict validation.
- **Done when:** application unit tests prove DTO boundaries and port contracts.

## Item 3 - Tenant and canonical validation

- **Scope:** `packages/core/revops/application/`, `packages/core/revops/domain/`, `tests/unit/`
- **Requires:** `packages/core/revops/application/`, `tests/unit/`
- **Closes:** 1 tasks.md checkbox
- **What:** validate relationship ownership and reuse SPEC-003 canonical account/contact resolution.
- **Done when:** unit tests prove cross-tenant rejection and alias-safe reads/writes.

## Item 4 - Persistence models

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`
- **Closes:** 1 tasks.md checkbox
- **What:** add Campaign and Touchpoint models plus Interaction and Opportunity fields, indexes and
  tenant foreign keys.
- **Done when:** model and metadata tests prove the declared schema and constraints.

## Item 5 - Additive migration

- **Scope:** `packages/core/revops/infrastructure/persistence/migrations/`, `tests/unit/infrastructure/`
- **Requires:** `packages/core/revops/infrastructure/persistence/migrations/`
- **Closes:** 1 tasks.md checkbox
- **What:** add the backward-compatible migration and backfill existing opportunity status to open.
- **Done when:** migration source inspection and offline migration assertions pass without destructive SQL.

## Item 6 - Repository adapters

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/unit/infrastructure/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`
- **Closes:** 1 tasks.md checkbox
- **What:** implement repository CRUD/query contracts while preserving existing unit-of-work boundaries.
- **Done when:** repository unit tests prove tenant filtering, relationship validation and append-only events.

## Item 7 - Docker migration round-trip

- **Scope:** `packages/core/revops/infrastructure/persistence/`, `tests/integration/`, `docs/specs/SPEC-005-crm-attribution-model/`
- **Requires:** `tests/integration/`, `packages/core/revops/infrastructure/persistence/migrations/`
- **Closes:** 1 tasks.md checkbox
- **What:** execute and test the real PostgreSQL migration round-trip.
- **Done when:** `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` and the targeted integration test pass.

## Item 8 - Existing-path compatibility

- **Scope:** `packages/core/revops/`, `apps/api/`, `apps/worker/`, `tests/unit/`, `tests/integration/`
- **Requires:** `packages/core/revops/infrastructure/persistence/`, `tests/integration/`
- **Closes:** 1 tasks.md checkbox
- **What:** adapt ingestion, deduplication and scoring only where new CRM relationships require it.
- **Done when:** existing ingestion, deduplication and prioritization integration tests pass with canonical resolution.

## Item 9 - Integration behavior

- **Scope:** `tests/integration/`, `packages/core/revops/infrastructure/persistence/`, `apps/api/`
- **Requires:** `tests/integration/`, `apps/api/`
- **Closes:** 1 tasks.md checkbox
- **What:** add relationship, lifecycle, idempotency and tenant-isolation integration coverage.
- **Done when:** `pytest tests/integration -q` passes with the new scenarios.

## Item 10 - Security and regression verification

- **Scope:** `tests/adversarial/`, `tests/unit/`, `evals/`, `docs/requirements/`
- **Requires:** `tests/adversarial/`, `evals/`
- **Closes:** 1 tasks.md checkbox
- **What:** prove untrusted metadata boundaries, tenant safety and no offline eval regression.
- **Done when:** adversarial tests, traceability checker and offline eval gate pass.

## Item 11 - Documentation and closeout

- **Scope:** `docs/specs/SPEC-005-crm-attribution-model/`, `docs/requirements/`, `.handoff/`
- **Requires:** `docs/specs/SPEC-005-crm-attribution-model/`, `docs/requirements/`
- **Closes:** 1 tasks.md checkbox
- **What:** record acceptance evidence, update the matrix and handoff, and close the spec.
- **Done when:** every task is evidenced and the full quality gate is green.

## Rules for the loop

- Never use a worktree, push, merge, or touch `main`.
- Return `architecture_required` before implementation at a genuine technical decision not covered
  by SPEC-005 `plan.md`; only the external supervisor may authorize a resume.
- Return `HUMAN_REQUIRED` for product, public-contract, dependency, destructive migration, security,
  verification, external-action or non-dominant decisions.
- Never edit this queue, the gate, the supervisor, AGENTS.md or an authorization artifact.
- Every item's implementation files must be committed before its checklist box is ticked.
