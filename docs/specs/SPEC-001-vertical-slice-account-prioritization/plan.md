# SPEC-001 — implementation plan

## Shape of the slice

```
POST /agent/runs ──> use case ──> LangGraph ──> [load context] ──> [score+reason] ──> [propose]
                                                                                          │
                                              policy: schema → rules → authz → risk ◄──────┘
                                                                                          │
                                                          interrupt (checkpoint persisted) ▼
POST /agent/runs/{id}/approve ──> resume ──> execute create_task ──> audit ──> done
```

## Layers

### domain (`packages/core/revops/domain/`)

Pure Python, no frameworks. This is where the slice earns its architecture.

- `entities/`: `Organization`, `User`, `Account`, `Contact`, `Opportunity`, `Interaction`, `Task`
- `values/`: `Score` (0–100 with a tier), `RiskLevel`, `EmailAddress`, `Domain` (normalised)
- `policies/risk.py`: `classify(tool_name, payload, confidence) -> RiskLevel`
- `policies/prioritization.py`: deterministic signals — days since last touch, open opportunity
  value, stage, engagement count. The LLM explains and ranks; it does not invent the arithmetic.
- `errors.py`: `PolicyViolationError`, `NotAuthorizedError`, `InvalidTransitionError`

### application (`packages/core/revops/application/`)

- `ports.py` (Protocols): `AccountRepository`, `TaskRepository`, `AuditTrail`, `LLMGateway`,
  `ApprovalRepository`, `AgentRunRepository`, `Clock`, `UnitOfWork`
- `use_cases/prioritize_accounts.py` — assemble bounded context and deterministic scores in one
  repository pass
- `use_cases/reason_about_accounts.py` — call the gateway, retry structured output at most three
  total attempts, validate trusted fields, and return ranked accounts plus a task draft
- `use_cases/propose_task.py` — build the proposed action, classify risk
- `use_cases/decide_approval.py` — approve / edit / reject, then execute
- `dto/`: Pydantic models, including `AccountScore` and `CreateTaskArgs` (`extra="forbid"`)
- `context/builder.py` — per-task context with a token budget; never the whole CRM

### infrastructure (`packages/core/revops/infrastructure/`)

- `persistence/`: SQLAlchemy models, repositories, Alembic migrations, `SqlAlchemyUnitOfWork`
- `agent/graph/`: nodes (`load_context`, `score_accounts`, `propose_action`, `execute_action`),
  minimal JSON-compatible state, conditional edge on the validated risk field,
  `AsyncPostgresSaver` checkpointer, and a dynamic `interrupt()` at the start of `execute_action`
- `agent/runner.py`: one lifecycle facade for start, stream, pending-interrupt lookup and resume;
  LangGraph `thread_id` is the string form of `agent_run_id`
- `agent/prompts/prioritize_accounts.v1.md` — versioned file, not a literal
- `llm/`: gateway with structured output + bounded schema retry; `FakeLLMGateway` for tests and CI
- `telemetry/`: structlog, run/cost accounting on `agent_runs`

### apps/api

`POST /agent/runs`, `GET /agent/runs/{id}/stream` (SSE), `GET /agent/runs`,
`POST /agent/runs/{id}/approve`. JWT auth, role check, `organization_id` resolved from the token and
pushed down to the repositories.

## Trade-offs

- **Heuristic + LLM, not pure LLM scoring.** Deterministic signals are reproducible and cheap; the
  model contributes explanation and ranking. Rejected: full LLM scoring — unmeasurable and expensive
  before evals exist.
- **HITL on a medium-risk tool.** More friction than the risk warrants, chosen because this slice
  exists to prove the approval and resume path. Documented so it can be relaxed later on evidence.
- **Postgres checkpointer, not memory.** Slower, but criterion 7 (survive a restart) is the whole
  point of a stateful agent. A memory checkpointer would make the tests pass and the system wrong.
- **Dynamic interrupt, not a static breakpoint.** `execute_action` calls `interrupt()` before any
  I/O and receives a validated decision through `Command(resume=...)`. Static
  `interrupt_before=` remains useful for debugging, not for the approval protocol.
- **Immutable run root plus append-only events.** `agent_runs` records identity and reproducibility
  inputs once. `agent_run_events` records interrupts and terminal metrics as self-contained rows;
  no audit row is updated in place.
- **Database-backed idempotency.** `action_id` and `task_id` are generated before the interrupt and
  checkpointed. Unique database identities make repeated or concurrent resumes converge on one
  Task, AgentAction and Approval.
- **No UI yet.** Verified through API integration tests. Rejected: building the UI in parallel —
  it doubles the surface before the backend contract is stable.
- **Pydantic stays out of the domain.** Slight duplication between domain values and DTOs, in
  exchange for a domain that never depends on a validation library. `lint-imports` enforces it.

## Test plan

- **unit**: prioritization signals at their boundaries; risk classification per tool; approval
  state machine (approve/edit/reject, and re-deciding an already-decided action); use cases against
  fakes; `FakeLLMGateway` returning malformed output to prove the retry-then-fail path.
- **integration**: repositories against real Postgres; the full run through the API; the interrupt
  → restart the process → resume path; repeated/concurrent resume idempotency; tenant isolation
  returning 403 with no leaked rows.
- **adversarial**: skip-approval prompt; cross-organization `create_task`; system-prompt extraction.

## Eval plan

Seed `tool_selection.jsonl` with ~10 cases including negatives ("summarise this account" must NOT
call `create_task`), and `lead_scoring.jsonl` with ~15 labelled accounts. Record the baseline;
enforce thresholds once the sets are large enough to be meaningful, and say so in the report.

## Order of work

1. Toolchain runs green on the empty skeleton
2. Domain + unit tests
3. Ports + use cases against fakes
4. Persistence + first migration + integration tests
5. Graph, prompts, fake gateway, interrupt/resume
6. API + auth + SSE
7. Policy and adversarial suite
8. Seed data, eval baseline, ADRs, handoff
