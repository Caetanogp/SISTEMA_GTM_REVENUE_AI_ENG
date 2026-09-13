# SPEC-005 tasks

Each checkbox is finishable in one sitting and must be ticked only after its evidence is observed.

## Domain and application

- [x] Define pure `Campaign`, `Touchpoint` and opportunity-status contracts - verified 2026-09-12 by `pytest tests/unit/domain/entities/test_attribution.py -q` and `python scripts/autonomous_gate.py` (`ruff`, `mypy`, `lint-imports`, `pytest`, `check_agent_docs`: `OK`)
- [x] Define tenant-scoped attribution DTOs and repository ports - verified 2026-09-12 by `pytest tests/unit/application/test_attribution.py -q` (5 passed), `ruff check packages/core/revops/application tests/unit/application`, `mypy packages/core/revops/application tests/unit/application` and `lint-imports`
- [x] Add organization and canonical-resolution validation - verified 2026-09-12 by `pytest tests/unit/application/test_attribution.py -q` (10 passed), `ruff check packages/core/revops/application tests/unit/application/test_attribution.py`, `mypy packages/core/revops/application tests/unit/application/test_attribution.py` and `lint-imports`

## Persistence

- [x] Add SQLAlchemy `Campaign` and `Touchpoint` models and fields on `Interaction`/`Opportunity` - verified 2026-09-12 by `pytest tests/unit/infrastructure/persistence/test_models.py -q` (10 passed), `ruff check packages/core/revops/infrastructure/persistence/models.py tests/unit/infrastructure/persistence/test_models.py`, `mypy packages/core/revops/infrastructure/persistence/models.py tests/unit/infrastructure/persistence/test_models.py` and `lint-imports`
- [x] Add additive Alembic migration with indexes, tenant foreign keys and `open` backfill - verified 2026-09-13 by `alembic upgrade b7c9d1e2f304:head --sql`, `pytest tests/unit/infrastructure/persistence/test_attribution_migration.py tests/unit/infrastructure/persistence/test_models.py -q` (13 passed), Ruff, mypy and lint-imports
- [x] Implement repository CRUD/query contracts without mixing existing unit-of-work boundaries - verified 2026-09-13 by `pytest tests/unit/infrastructure/persistence/test_repositories.py tests/unit/infrastructure/persistence/test_models.py -q` (31 passed), scoped Ruff, mypy and `lint-imports`
- [x] Run migration round-trip against Docker PostgreSQL - verified 2026-09-13 against local Docker PostgreSQL by `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` and `pytest tests/integration/test_attribution_migration_round_trip.py -q` (1 passed)

## Compatibility and verification

- [x] Adapt affected ingestion, deduplication or scoring reads/writes only where required - verified
  2026-09-13 by `alembic check` (no new operations), migration integration tests (5 passed), the
  existing ingestion/deduplication/prioritization integration set (19 passed), and
  `python scripts/autonomous_gate.py` (Ruff, mypy, lint-imports, unit/architecture tests and agent
  docs green); implementation commit `2f8b190`
- [x] Add relationship, lifecycle, idempotency and tenant-isolation integration tests - verified 2026-09-13 by `pytest tests/integration -q` (36 passed), `ruff check packages/core/revops/infrastructure/persistence/repositories.py tests/integration/test_attribution_behavior.py`, `ruff format --check packages/core/revops/infrastructure/persistence/repositories.py tests/integration/test_attribution_behavior.py`, `mypy packages/core/revops/infrastructure/persistence/repositories.py tests/integration/test_attribution_behavior.py` and `lint-imports`; implementation commit `32e7b78`
- [x] Confirm adversarial/security behavior and no offline eval regression - verified 2026-09-13 by `pytest tests/adversarial -q` (11 passed), `python scripts/check_pdf_traceability.py` (86 rows, pages 1-20 covered), `python -m evals.gate` (tool_selection 14/14; lead_scoring 15/15), and `python scripts/autonomous_gate.py` (Ruff, mypy, lint-imports, unit/architecture tests and agent docs green); implementation commit `324e62d`
- [ ] Update traceability evidence and complete closeout - verified by checker, full gate and `.handoff/STATE.md`
