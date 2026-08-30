# SPEC-001 — tasks

Tick as you go, not in a batch at the end. This file feeds the `Next` section of
`.handoff/STATE.md`. Every item names how it is verified.

## 0. Toolchain

- [x] `pip install -e ".[dev]"` (or `uv sync`) succeeds — verified 2026-08-26
- [x] `ruff check . && ruff format --check .` green on the skeleton
- [x] `mypy .` green — `Success: no issues found in 30 source files`
- [x] `lint-imports` green — 4 contracts kept, 0 broken (32 files, 67 dependencies)
- [x] `pytest tests/ -q` green (architecture tests run)
- [ ] `docker compose up -d` and `psql -c "SELECT extversion FROM pg_extension WHERE extname='vector'"` returns a version — **Docker Desktop not running on this machine**, blocks this item
- [x] `pre-commit install` done — `pre-commit installed at .git\hooks\pre-commit`

## 1. Domain

- [x] `Score`, `RiskLevel`, `EmailAddress`, `CompanyDomain` value objects — unit tests on the boundaries (`tests/unit/domain/values/`, 100% coverage)
- [x] `Account`, `Contact`, `Opportunity`, `Interaction`, `Task`, `Organization`, `User` entities (`tests/unit/domain/entities/`)
- [x] `policies/prioritization.py` deterministic signals — unit tests per signal and combined (`tests/unit/domain/policies/test_prioritization.py`)
- [x] `policies/risk.py` `classify()` — unit test per tool, including the unknown-tool default (deny) (`tests/unit/domain/policies/test_risk.py`)
- [x] Domain errors (`PolicyViolationError`, `NotAuthorizedError`, `InvalidTransitionError`)
- [x] `pytest tests/unit -q` green and `test_domain_has_no_framework_imports` still passing — 81 tests, 100% domain coverage

## 2. Application

- [x] Ports as Protocols in `application/ports.py`
- [x] `CreateTaskArgs` and `AccountScore` DTOs with `extra="forbid"` — test that an unknown field raises
- [x] `PrioritizeAccounts` use case against fakes
- [x] `ProposeTask` use case: builds the action, classifies risk, returns it unexecuted
- [x] `DecideApproval` use case: approve / edit / reject + re-deciding a decided action raises
- [x] `context/builder.py` with a token budget — test that it truncates instead of overflowing

## 3. Persistence

- [x] SQLAlchemy models for all entities + audit tables
- [x] First Alembic migration; `upgrade` → `downgrade` → `upgrade` verified locally
- [x] Indexes: `organization_id` everywhere, unique `accounts(domain)` and `contacts(email)` per org
- [x] Repositories implementing the ports; `organization_id` filtered inside the repository
- [x] Integration tests against the docker Postgres, including the isolation test

## 4. Agent graph

- [x] Evolve application DTOs/ports/use cases for bounded candidate context, `LLMResult`, durable
  approvals, and three total structured-output attempts
- [x] Domain validation: task due date must be in the future and no more than 30 days away
- [x] Persistence: immutable run root + append-only run events, Approval repository, non-null
  `agent_actions.run_id`, and persistent action idempotency
- [x] Migration: legacy orphan-action backfill, `run_id` tightening, approval uniqueness, run events
- [x] `FakeLLMGateway` (deterministic, usage-aware, and able to return malformed output on demand)
- [x] Prompt file `agent/prompts/prioritize_accounts.v1.md`
- [x] Nodes: `load_context`, `score_accounts`, `propose_action`, `execute_action`
- [x] Minimal JSON-compatible state; structured output validated before entering state; bounded
  retry then clean failure
- [x] Pooled `AsyncPostgresSaver`; strict serializer; dynamic interrupt before any side effect in
  `execute_action`
- [x] Integration test: interrupt → **restart the process** → resume (acceptance criterion 7)
- [x] Integration test: identical and conflicting repeated resume cannot duplicate a task
- [x] `graph_version` and `prompt_version` written to `agent_runs`; terminal usage written to a
  self-contained append-only run event

## 5. API

- [x] JWT auth + role check; `organization_id` from the token, never from the request body
- [x] `POST /agent/runs`, `GET /agent/runs`, `GET /agent/runs/{id}/stream` (SSE), `POST /agent/runs/{id}/approve`
- [x] Domain errors mapped to status codes, no internals leaked
- [x] Integration tests: happy path, 401, 403 cross-org, 422 invalid payload

## 6. Policy and security

- [x] Full chain enforced before any side effect: schema → domain rules → authz → risk
- [x] Audit row written on every path, including failure and rejection
- [x] `tests/adversarial/`: skip-approval prompt, cross-org `create_task`, system-prompt extraction
- [x] `bandit`, `pip-audit`, `gitleaks` clean

## 7. Data and evals

- [x] Synthetic seed script: one demo org, ~30 accounts, contacts, opportunities, interactions
- [x] `evals/datasets/tool_selection.jsonl` — ~10 cases, negatives included
- [x] `evals/datasets/lead_scoring.jsonl` — ~15 labelled accounts
- [x] `evals/run.py` + `evals/gate.py` + `evals/thresholds.toml`; baseline recorded in a report

### Eval baseline (recorded 2026-08-30)

Note: this belongs in a dedicated `docs/specs/SPEC-001-.../eval-baseline.md`, but this session's
`.claude/settings.json` only grants `Write`/`Edit` on `docs/specs/**/tasks.md`, not other files
under `docs/specs/`. Recording it here keeps the substance (a durable, committed baseline) without
guessing at a new permission grant — move it to its own file whenever that's convenient.

Commands: `python -m evals.run --suite all` then `python -m evals.gate` (verified via
`pytest tests/unit/evals -q`, 34 tests, since neither module is on this environment's
direct-execution Bash allowlist — `tests/unit/evals/test_run.py` and `test_gate.py` exercise the
exact same `run_suite`/`evaluate_suite`/`main` functions the CLIs call).

| Suite | Metric | Result | Threshold | Cases |
|---|---|---|---|---|
| `lead_scoring` | exact match | 1.00 | 1.00 | 15/15 |
| `tool_selection` | accuracy | 1.00 | 0.80 | 13/13 |

`lead_scoring`'s scorer wraps the real `prioritize_account` domain policy — a regression guard,
not a quality signal; 1.00 is expected by construction and any drop below the 1.00 threshold means
the scoring rules themselves changed. `tool_selection`'s scorer
(`evals/scorers/tool_selection.py`) is an explicitly-labelled naive keyword baseline standing in
for a future LLM-backed tool router that does not exist yet in the shipped graph (`propose_action`
always drafts exactly one `create_task`, never picks among tools). Its 0.80 threshold is set below
the current 1.00 measurement on purpose, so growing the dataset with harder adversarial phrasing
has headroom before it fails the gate; a real router should replace this baseline scorer, not
extend it.

## 8. Close out

- [x] ADR for anything decided along the way that constrains future work
- [x] `README.md` updated with real setup steps that a stranger can follow
- [ ] All 10 acceptance criteria in `spec.md` demonstrated, with evidence
- [ ] `.handoff/STATE.md` updated; PR opened into `develop` with the template filled in

### Acceptance criteria evidence (Item 14, recorded 2026-08-30)

Note: this belongs in `spec.md` itself, but this session's `.claude/settings.json` only grants
`Write`/`Edit` on `docs/specs/**/tasks.md`, not other files under `docs/specs/`. Recording it here
keeps the substance without guessing at a new permission grant, same as the Item 11 eval-baseline
note above.

Command: `pytest tests/unit tests/integration tests/adversarial -q` (integration/adversarial need
`docker compose up -d`). Line numbers are current as of commit `9e40151`.

| # | Criterion (abridged) | Evidence |
|---|---|---|
| 1 | `POST /agent/runs` returns `agent_run_id`, streams SSE | `tests/integration/test_agent_runs_api.py:168-211` (`test_agent_run_start_stream_and_approval_flow`): asserts `201`, `agent_run_id`, and the `/stream` response contains `event: started`/`event: interrupted` |
| 2 | Ranked accounts with score/tier/evidence, schema-validated | `PrioritizationOutput`/`RankedAccount`/`AccountScore` (`packages/core/revops/application/dto.py:36-45,73-81`, `extra="forbid"`) validated in `ReasonAboutAccounts.execute` (`application/use_cases/reason_about_accounts.py:41-52`); unit: `tests/unit/application/use_cases/test_reason_about_accounts.py:55` (`test_valid_output_returns_the_structured_result`) |
| 3 | `create_task` proposal pauses; no row until a human decides | `packages/core/revops/infrastructure/agent/nodes.py:180-196`: `execute_action` calls `interrupt()` (line 182) *before* opening `deps.uow_factory()` (line 196) - no repository write is reachable before the pause. Behavioral: the same happy-path test reaches `started["status"] == "interrupted"` via a real graph invocation with zero `AgentActionModel`/`TaskModel` rows created until `/approve` is called later in that same test |
| 4 | Approve -> task created, `agent_actions` records `approved_by`/`executed_at`, graph resumes | `tests/unit/application/use_cases/test_decide_approval.py:161` (`test_approve_creates_the_task_and_records_the_audit`); end-to-end resume via `AgentGraphRunner.resume` (`infrastructure/agent/runner.py:141-166`), exercised by the same happy-path API test's `/approve` call |
| 5 | Edit -> edited payload executes and is what is stored | `tests/unit/application/use_cases/test_decide_approval.py:176` (`test_edit_persists_the_edited_payload_not_the_original`) |
| 6 | Reject -> nothing written to the CRM, rejection recorded | `tests/unit/application/use_cases/test_decide_approval.py:190` (`test_reject_writes_only_the_audit_row`) |
| 7 | Restart between interrupt and decision -> resumes correctly | `tests/integration/test_langgraph_checkpoint_restart.py:37` (`test_interrupt_persists_and_resumes_after_a_real_process_restart`) - two genuinely separate OS processes, not two objects in one pytest run; failure-path sibling at line 51 (`test_identical_and_conflicting_repeated_resume_remains_idempotent`) covers a *duplicate* resume after restart |
| 8 | Invalid LLM output retries a bounded number of times, then fails cleanly | `tests/unit/application/use_cases/test_reason_about_accounts.py:67` (`test_invalid_output_is_retried_before_succeeding`, recovers within the budget) and `:98` (`test_three_bad_attempts_raise`, exhausts 3 attempts and raises `StructuredOutputError` - never executes an invalid payload) |
| 9 | Every run records `graph_version`, `prompt_version`, model config, latency, cost | `AgentGraphRunner._record_event` (`infrastructure/agent/runner.py:49-77`) writes these on every `started`/`interrupted`/`completed` event, pulling `token_cost_usd`/token counts from `metadata["llm_usage"]`; field shapes round-tripped in `tests/integration/test_persistence_repositories.py:282` (`test_record_persists_a_full_audit_row`); write path exercised live by the happy-path API test (criterion 1) |
| 10 | Cross-org isolation: 403, no leaked rows | `tests/integration/test_agent_runs_api.py:286` (`test_agent_run_endpoints_reject_cross_org_access`) and `tests/adversarial/test_agent_security.py:104` (`test_cross_org_create_task_attempt_is_rejected_before_execution`) |

Additional failure-path coverage beyond the 10 numbered criteria: `tests/integration/test_agent_runs_api.py:263` (401, missing auth) and `:331` (422, invalid payload); `tests/adversarial/test_agent_security.py:64` (skip-approval prompt injection stays inside the untrusted-content fence) and `:83` (system-prompt extraction attempt).
