# SPEC-009: Bounded Single-Agent Tool Runtime Tasks

- [ ] Record the agreed bounded runtime, refusal-on-ambiguity, no-migration, and public-contract
  constraints in an ADR or implementation note under `docs/decisions/` - verified by the recorded
  decision and review against `spec.md` and `plan.md`
- [ ] Add pure runtime outcome, tool-budget, and deny-by-default policy contracts under
  `packages/core/revops/domain/` - verified by focused domain tests for supported outcomes, stable
  failures, five-call limit, and one-write limit
- [ ] Add strict runtime request, tool-call, result, failure, and evidence DTOs under
  `packages/core/revops/application/` - verified by schema tests for forbidden fields, tenant
  injection, and sanitized metadata
- [ ] Add typed application ports for the three existing tools and the bounded dispatcher - verified
  by protocol tests and `mypy .`
- [ ] Implement the runtime dispatcher with structured model output, allowlist/risk validation,
  tenant authorization, schema validation, and deterministic refusal - verified by application unit
  tests for unknown, malformed, cross-tenant, unsupported, and ambiguous inputs
- [ ] Adapt `search_accounts` and `get_account_context` to existing account/context behavior without
  duplicating business rules - verified by unit tests and tenant-scoped integration assertions
- [ ] Adapt `create_task` to the existing `ProposeTask`/`DecideApproval` path with no write before
  HITL - verified by unit tests and the approval integration flow
- [ ] Extend checkpoint state and graph routing to carry runtime outcome, call counters, tool
  evidence, and pending approval while preserving serialized compatibility - verified by state
  serialization tests and `tests/integration/test_langgraph_checkpoint_restart.py`
- [ ] Enforce the five-call and one-write budgets outside model output - verified by sixth-call
  rejection and second-write rejection with no adapter invocation
- [ ] Preserve approve/edit/reject semantics and make identical approval replay idempotent while
  conflicting replay fails closed - verified by integration tests and task-row count assertions
- [ ] Append sanitized route/tool/failure evidence through the existing agent-run journal and audit
  boundary - verified by lifecycle tests asserting append-only rows and absence of raw secrets/PII
- [ ] Add deterministic `agent_tool_runtime_contract` dataset and scorer for routing, allowlist,
  schema, tenant, budget, HITL, replay, and fencing cases - verified by `python -m evals.run --suite
  agent_tool_runtime_contract` at exactly 1.00 without credentials or network
- [ ] Extend adversarial coverage for prompt injection, tool confusion, cross-tenant fields, budget
  bypass, write-before-approval, and replay - verified by `pytest tests/adversarial -q`
- [ ] Wire the dispatcher in `apps/api/runtime.py` without changing authenticated `/agent/runs`
  start, stream, or approval response contracts - verified by API integration tests
- [ ] Update PDF traceability, security documentation, and prompt/version evidence with concrete
  file:line references - verified by `python scripts/check_pdf_traceability.py` and
  `python scripts/check_agent_docs.py`
- [ ] Complete full verification and closeout - verified by `ruff check .`, `ruff format --check .`,
  `mypy .`, `lint-imports`, `pytest tests/unit -q`, `pytest tests/integration -q`,
  `pytest tests/adversarial -q`, `python -m evals.run --suite all`, `gitleaks detect --no-git`, and
  `python scripts/autonomous_gate.py`
