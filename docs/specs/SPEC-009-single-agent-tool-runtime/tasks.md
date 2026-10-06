# SPEC-009: Bounded Single-Agent Tool Runtime Tasks

- [x] Record the agreed bounded runtime, refusal-on-ambiguity, no-migration, and public-contract
  constraints in an ADR or implementation note under `docs/decisions/` - verified by the recorded
  decision and review against `spec.md` and `plan.md`
- [x] Add pure runtime outcome, tool-budget, and deny-by-default policy contracts under
  `packages/core/revops/domain/` - verified by focused domain tests for supported outcomes, stable
  failures, five-call limit, and one-write limit
- [x] Add strict runtime request, tool-call, result, failure, and evidence DTOs under
  `packages/core/revops/application/` - verified by schema tests for forbidden fields, tenant
  injection, and sanitized metadata
- [x] Add typed application ports for the three existing tools and the bounded dispatcher - verified
  by protocol tests and `mypy .`
- [x] Implement the runtime dispatcher with structured model output, allowlist/risk validation,
  tenant authorization, schema validation, and deterministic refusal - verified by application unit
  tests for unknown, malformed, cross-tenant, unsupported, and ambiguous inputs
- [x] Adapt `search_accounts` and `get_account_context` to existing account/context behavior without
  duplicating business rules - verified by unit tests and tenant-scoped integration assertions
- [x] Adapt `create_task` to the existing `ProposeTask`/`DecideApproval` path with no write before
  HITL - verified by unit tests and the approval integration flow
- [x] Extend checkpoint state and graph routing to carry runtime outcome, call counters, tool
  evidence, and pending approval while preserving serialized compatibility - verified by state
  serialization tests and `tests/integration/test_langgraph_checkpoint_restart.py`
- [x] Enforce the five-call and one-write budgets outside model output - verified by sixth-call
  rejection and second-write rejection with no adapter invocation
- [x] Preserve approve/edit/reject semantics and make identical approval replay idempotent while
  conflicting replay fails closed - verified by integration tests and task-row count assertions
- [x] Append sanitized route/tool/failure evidence through the existing agent-run journal and audit
  boundary - verified by lifecycle tests asserting append-only rows and absence of raw secrets/PII
- [x] Add deterministic `agent_tool_runtime_contract` dataset and scorer for routing, allowlist,
  schema, tenant, budget, HITL, replay, and fencing cases - verified by `python -m evals.run --suite
  agent_tool_runtime_contract` at exactly 1.00 without credentials or network
- [x] Extend adversarial coverage for prompt injection, tool confusion, cross-tenant fields, budget
  bypass, write-before-approval, and replay - verified by `pytest tests/adversarial -q`
- [x] Wire the dispatcher in `apps/api/runtime.py` without changing authenticated `/agent/runs`
  start, stream, or approval response contracts - verified by API integration tests
- [x] Update PDF traceability, security documentation, and prompt/version evidence with concrete
  file:line references - verified by `python scripts/check_pdf_traceability.py` and
  `python scripts/check_agent_docs.py`
- [x] Complete full verification and closeout - verified 2026-10-06 by `ruff check .`,
  `ruff format --check .`, `mypy .`, `lint-imports`, `pytest tests/unit -q` (451 passed),
  `pytest tests/integration -q` (47 passed with 3 known SQLAlchemy cleanup warnings),
  `pytest tests/adversarial -q` (26 passed), `python -m evals.run --suite all` (all six suites
  1.00), `python scripts/check_pdf_traceability.py`, `python scripts/check_agent_docs.py`,
  `gitleaks detect --no-git` (no leaks), and `python scripts/autonomous_gate.py` (full gate green)
