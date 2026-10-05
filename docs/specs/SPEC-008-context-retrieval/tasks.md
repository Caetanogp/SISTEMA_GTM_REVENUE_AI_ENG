# SPEC-008: Task-Scoped Knowledge Retrieval Tasks

- [x] Record the approved retrieval contract, compatibility failure behavior, tenant boundary, and
  no-migration baseline in an ADR under `docs/decisions/` - verified by the ADR covering the
  decisions in `plan.md`
- [x] Add pure retrieval value objects and invariants under `packages/core/revops/domain/` -
  verified by focused domain unit tests for limits, budgets, scores, provenance, and embedding
  spaces
- [x] Add retrieval DTOs, `KnowledgeRetrievalRepository`, and typed errors under
  `packages/core/revops/application/` - verified by mypy, import-linter, and contract unit tests
- [x] Implement `RetrieveKnowledge` with trusted organization context, one configured query
  embedding, bounded limits, and typed provider/compatibility failures - verified by application
  unit tests with fake ports
- [x] Implement the task knowledge context assembler with untrusted-data fencing, provenance, token
  budgeting, and omission reporting - verified by context unit tests and injection-shaped cases
- [x] Implement active embedding-space resolution in the persistence adapter - verified by
  `tests/integration/test_knowledge_retrieval.py` and the Item 3 gate
- [x] Implement the bounded pgvector candidate query with active revision and ready-state filters -
  verified by exact materialized eligibility in `packages/core/revops/infrastructure/persistence/knowledge_repositories.py`
  and the Item 3 gate
- [x] Enforce organization override before ranking and top-k selection - verified by the adapter's
  pre-ranking source selection and unit/integration contract coverage
- [x] Return complete source provenance and deterministic score/tie ordering - verified by
  `tests/integration/test_knowledge_retrieval.py`, domain tests, and the Item 3 gate
- [x] Wire the retrieval use case through the internal composition root without exposing arbitrary
  corpus selection - verified by application wiring tests and tenant authorization tests
- [x] Add adversarial coverage for injection-shaped passages, secret-shaped passages, cross-tenant
  IDs, historical revisions, invalid limits, and invalid budgets - verified by `pytest
  tests/adversarial -q`
- [ ] Add the deterministic `rag_retrieval_contract` dataset and scorer - verified by
  `python -m evals.run --suite rag_retrieval_contract` at 1.00 without credentials or network
- [ ] Document the optional live retrieval smoke and cost confirmation behavior - verified by the
  smoke command refusing unconfirmed or missing live configuration
- [ ] Update PDF traceability for retrieval, source attribution, and retrieval evaluation -
  verified by `python scripts/check_pdf_traceability.py`
- [ ] Complete security review, handoff evidence, full verification, and the autonomous gate -
  verified by `docs/playbooks/verify-before-done.md` and `python scripts/autonomous_gate.py`
