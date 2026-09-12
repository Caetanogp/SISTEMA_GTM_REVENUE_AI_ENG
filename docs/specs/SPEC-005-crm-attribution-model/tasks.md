# SPEC-005 tasks

Each checkbox is finishable in one sitting and must be ticked only after its evidence is observed.

## Domain and application

- [x] Define pure `Campaign`, `Touchpoint` and opportunity-status contracts - verified 2026-09-12 by `pytest tests/unit/domain/entities/test_attribution.py -q` and `python scripts/autonomous_gate.py` (`ruff`, `mypy`, `lint-imports`, `pytest`, `check_agent_docs`: `OK`)
- [ ] Define tenant-scoped attribution DTOs and repository ports - verified by application unit tests
- [ ] Add organization and canonical-resolution validation - verified by cross-tenant and alias unit tests

## Persistence

- [ ] Add SQLAlchemy `Campaign` and `Touchpoint` models and fields on `Interaction`/`Opportunity` - verified by model tests
- [ ] Add additive Alembic migration with indexes, tenant foreign keys and `open` backfill - verified by migration inspection
- [ ] Implement repository CRUD/query contracts without mixing existing unit-of-work boundaries - verified by persistence unit tests
- [ ] Run migration round-trip against Docker PostgreSQL - verified by `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`

## Compatibility and verification

- [ ] Adapt affected ingestion, deduplication or scoring reads/writes only where required - verified by existing integration tests
- [ ] Add relationship, lifecycle, idempotency and tenant-isolation integration tests - verified by `pytest tests/integration -q`
- [ ] Confirm adversarial/security behavior and no offline eval regression - verified by `pytest tests/adversarial -q` and `python -m evals.gate`
- [ ] Update traceability evidence and complete closeout - verified by checker, full gate and `.handoff/STATE.md`
