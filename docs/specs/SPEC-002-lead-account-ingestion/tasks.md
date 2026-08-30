# SPEC-002 task checklist

## Specification and loop

- [x] Generalize `scripts/autonomous_gate.py` for queue-selected task files and add its unit tests.
- [x] Replace the SPEC-001 queue with scoped SPEC-002 work items and verify the pilot gate.

## Domain and application

- [x] Add pure import job/item state models and transition tests in `packages/core/revops/domain/`.
- [x] Add canonical ingestion/enrichment DTOs, ports, and unit-tested application use cases.

## Persistence and adapters

- [x] Add SQLAlchemy ingestion/enrichment models, repositories, and an additive Alembic migration.
- [x] Verify the migration with `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head`.
- [x] Add strict CSV parsing and deterministic synthetic enrichment adapters with unit tests.
- [ ] Add the Celery dispatch adapter and `apps/worker` composition root with duplicate-delivery tests.

## API and security

- [ ] Add admin-only JSON/CSV staging, confirmation, status, and paginated item routes.
- [ ] Add API integration coverage for partial success, idempotency, queue failure, and tenant isolation.
- [ ] Add adversarial coverage for untrusted CSV/JSON, authorization bypass, and PII-safe failures.

## Closeout

- [ ] Record the Celery/outbox phasing decision in an ADR and update README setup instructions.
- [ ] Map every acceptance criterion to observed test/command evidence and update `.handoff/STATE.md`.
- [ ] Run `docs/playbooks/verify-before-done.md` in full and prepare the feature branch for review.
