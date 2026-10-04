# Autonomous work queue

The only source of work for the SPEC-007 unattended loop. Items run in order and remain inside
their declared file scope. `scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-007-rag-ingestion/tasks.md`

## Item 1 - Domain contracts and chunking pilot

- **Scope:** `packages/core/revops/domain/`, `tests/unit/domain/`
- **Requires:** agreed SPEC-007 docs and no unresolved architecture decision
- **Closes:** 3 tasks.md checkboxes
- **What:** implement pure validation, lifecycle, normalization, chunking, limits, and hashes.
- **Done when:** focused domain tests pass and no infrastructure dependency enters the domain.

## Item 2 - Application ports and DTOs

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** Item 1
- **Closes:** task 3
- **What:** define use-case contracts, ports, DTOs, and authorization-facing boundaries.
- **Done when:** signatures and unit tests enforce the planned contracts.

## Item 3 - Persistence schema

- **Scope:** `packages/core/revops/infrastructure/`, `alembic/`, `tests/integration/`
- **Requires:** Items 1-2
- **Closes:** task 5
- **What:** add immutable knowledge/version/chunk/revision models and pgvector migration/indexes.
- **Done when:** migration upgrade/downgrade and model tests pass without destructive downgrade.

## Item 4 - Repositories and revisions

- **Scope:** `packages/core/revops/infrastructure/`, `tests/integration/`
- **Requires:** Item 3
- **Closes:** task 6
- **What:** implement tenant scope, idempotency, immutable history, and atomic corpus revisions.
- **Done when:** isolation, replay/conflict, failure atomicity, and append-only tests pass.

## Item 5 - Embedding providers

- **Scope:** `packages/core/revops/infrastructure/`, `tests/unit/infrastructure/`
- **Requires:** Item 2
- **Closes:** 2 tasks.md checkboxes
- **What:** add deterministic offline fake and bounded explicit OpenAI adapter.
- **Done when:** batch, timeout, retry, dimension, determinism, and no-fallback tests pass.

## Item 6 - Lifecycle use cases

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** Items 2, 4, and 5
- **Closes:** task 9
- **What:** orchestrate submit, confirm, process, publish, fail, retire, and activate operations.
- **Done when:** all transitions and authorization rules are covered.

## Item 7 - Worker

- **Scope:** `.env.example`, `apps/worker/`, `packages/core/revops/application/`, `packages/core/revops/infrastructure/`, `tests/unit/application/`, `tests/unit/apps/worker/`, `tests/unit/infrastructure/`, `tests/integration/`
- **Requires:** Item 6
- **Closes:** task 10
- **What:** run bounded asynchronous processing with classified retries and append-only safe audit
  events under ADR-0013.
- **Done when:** Celery task tests prove retry, replay, provenance, and atomic publication behavior.

## Item 8 - Admin API

- **Scope:** `apps/api/`, `packages/core/revops/application/`, `tests/integration/`
- **Requires:** Item 6
- **Closes:** task 11
- **What:** expose tenant-scoped JSON admin endpoints and idempotency semantics.
- **Done when:** API contract, auth, metadata-list, and cross-tenant tests pass.

## Item 9 - Platform seed

- **Scope:** `apps/platform_seed.py`, `packages/core/revops/application/`, `packages/core/revops/infrastructure/`, `tests/unit/application/`, `tests/unit/infrastructure/`, `tests/unit/apps/`, `tests/integration/`, `docs/decisions/ADR-0015-platform-seed-loading-and-attribution.md`, `docs/specs/SPEC-007-rag-ingestion/plan.md`, `.handoff/log/2026-10-03-codex-item9-design.md`
- **Requires:** Items 6-8; implementation evidence in `apps/platform_seed.py`, `packages/core/revops/infrastructure/knowledge_seed/`, `tests/integration/test_platform_seed.py`
- **Closes:** task 12
- **What:** implement the approved ADR-0015 seed contract, deployment attribution, conditional
  downgrade, serialized revision updates, and recovery without exposing platform mutation.
- **Done when:** application, concurrency, SQL attribution, migration, worker, tenant override,
  and sanitized CLI tests pass; observe the Item 9 gate before ticking its task.

## Item 10 - Integration and adversarial coverage

- **Scope:** `tests/integration/`, `tests/adversarial/`
- **Requires:** Items 1-9
- **Closes:** task 13
- **What:** cover end-to-end ingestion, isolation, immutable audit, injection-shaped content, and secrets.
- **Done when:** targeted integration and adversarial suites pass.

## Item 11 - Evals and smoke documentation

- **Scope:** `evals/`, `scripts/`, `docs/`
- **Requires:** Items 1-10
- **Closes:** task 14
- **What:** add the mandatory offline contract eval and optional cost-confirmed live smoke.
- **Done when:** offline score is exactly 1.00 and live smoke is never required by CI.

## Item 12 - Closeout and verification

- **Scope:** `docs/`, `.handoff/`, `tests/`, `packages/`, `apps/`
- **Requires:** Items 1-11
- **Closes:** task 15
- **What:** complete traceability, security review, handoff evidence, and the full gate.
- **Done when:** every required command passes with file:line evidence and a commit SHA.

## Loop rules

- Never edit this queue, the gate, supervisor controls, or `AGENTS.md` from an executor item.
- Return `architecture_required` for an uncovered component shape, state-machine edge, or other
  decision with multiple defensible implementations; return `HUMAN_REQUIRED` for product scope,
  destructive, security, dependency, or unverifiable decisions.
- No push, merge, work on `main`/`develop`, skipped tests, weakened checks, or checkout temp files.
- Commit one logical item before checking its task evidence.
