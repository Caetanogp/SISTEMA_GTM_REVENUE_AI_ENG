# SPEC-007 tasks

- [x] Reconcile SPEC-006 closeout, roadmap, handoff, and PDF traceability in `docs/` and `.handoff/` - verified by `python scripts/check_pdf_traceability.py` (86 rows, pages 1-20 covered)
- [ ] Define pure knowledge categories, language, scope, lifecycle, and validation contracts in `packages/core/revops/domain/` - verified by domain unit tests
- [ ] Define application DTOs, repository/UoW/embedding/dispatch ports in `packages/core/revops/application/` - verified by import and application unit tests
- [ ] Implement deterministic normalization, metadata validation, heading/paragraph chunking, limits, and hashes - verified by chunking unit tests
- [ ] Add knowledge SQLAlchemy models, pgvector indexes, and additive migration - verified by migration tests
- [ ] Implement tenant-scoped repositories, idempotency, immutable versions, and corpus revisions - verified by integration tests
- [ ] Implement deterministic offline fake embeddings - verified by deterministic vector tests
- [ ] Implement bounded OpenAI embedding adapter with explicit configuration - verified by adapter unit tests
- [ ] Implement confirmation, processing, publication, failure, retirement, and activation use cases - verified by application tests
- [ ] Implement Celery processing task and safe audit/error handling - verified by worker integration tests
- [ ] Implement tenant-scoped admin API routes and schemas - verified by API tests
- [ ] Implement trusted platform seed loading without tenant mutation - verified by seed integration tests
- [ ] Add migration, API, worker, tenant-isolation, and append-only integration coverage - verified by `pytest tests/integration -q`
- [ ] Add adversarial cases, `rag_ingestion_contract` eval, and optional live smoke documentation - verified by adversarial/eval commands
- [ ] Complete PDF traceability, security review, handoff evidence, and full verification - verified by `python scripts/autonomous_gate.py`
