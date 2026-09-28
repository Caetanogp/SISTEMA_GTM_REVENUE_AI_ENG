# SPEC-007 tasks

- [x] Reconcile SPEC-006 closeout, roadmap, handoff, and PDF traceability in `docs/` and `.handoff/` - verified by `python scripts/check_pdf_traceability.py` (86 rows, pages 1-20 covered)
- [x] Define pure knowledge categories, language, scope, lifecycle, and validation contracts in `packages/core/revops/domain/` - verified by `mypy packages/core/revops/domain tests/unit/domain/entities/test_knowledge.py` and domain tests (`128 passed`)
- [x] Define application DTOs, repository/UoW/embedding/dispatch ports in `packages/core/revops/application/` - verified by `pytest tests/unit/application -q` (`70 passed`), `mypy .`, and `lint-imports`
- [x] Implement deterministic normalization, metadata validation, heading/paragraph chunking, limits, and hashes - verified by `pytest tests/unit/domain tests/architecture -q` (`128 passed`)
- [x] Add knowledge SQLAlchemy models, pgvector indexes, and additive migration - verified by `pytest tests/integration/test_migration_history_reconciliation.py tests/integration/test_attribution_migration_round_trip.py -q`, `python -m alembic upgrade head`, and `python -m alembic check` (`d8e9f0a1b2c3`)
- [x] Implement tenant-scoped repositories, idempotency, immutable versions, and corpus revisions - verified by `pytest tests/integration/test_knowledge_revision_persistence.py tests/integration/test_migration_history_reconciliation.py -q` (`6 passed`), full integration suite (`38 passed`), `mypy .`, and `lint-imports`
- [ ] Implement deterministic offline fake embeddings - verified by deterministic vector tests
- [ ] Implement bounded OpenAI embedding adapter with explicit configuration - verified by adapter unit tests
- [ ] Implement confirmation, processing, publication, failure, retirement, and activation use cases - verified by application tests
- [ ] Implement Celery processing task and safe audit/error handling - verified by worker integration tests
- [ ] Implement tenant-scoped admin API routes and schemas - verified by API tests
- [ ] Implement trusted platform seed loading without tenant mutation - verified by seed integration tests
- [ ] Add migration, API, worker, tenant-isolation, and append-only integration coverage - verified by `pytest tests/integration -q`
- [ ] Add adversarial cases, `rag_ingestion_contract` eval, and optional live smoke documentation - verified by adversarial/eval commands
- [ ] Complete PDF traceability, security review, handoff evidence, and full verification - verified by `python scripts/autonomous_gate.py`
