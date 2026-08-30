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

- [ ] ADR for anything decided along the way that constrains future work
- [ ] `README.md` updated with real setup steps that a stranger can follow
- [ ] All 10 acceptance criteria in `spec.md` demonstrated, with evidence
- [ ] `.handoff/STATE.md` updated; PR opened into `develop` with the template filled in
