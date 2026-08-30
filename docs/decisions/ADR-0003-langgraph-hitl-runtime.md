# ADR-0003: LangGraph HITL runtime, durable decisions, and immutable run accounting

- **Status:** accepted
- **Date:** 2026-08-30
- **Context spec:** SPEC-001

## Context

SPEC-001 fixes four graph nodes and requires a Postgres checkpoint to survive a process restart,
but it did not decide the checkpoint state, thread identity, interrupt API, transaction owner, or
how a human decision remains exactly-once after Python memory is lost. The persistence phase also
left `agent_actions.run_id` nullable and `PendingApproval.decided` in memory on purpose, for this
graph phase to close.

The installed runtime is LangGraph 1.1.10 with `langgraph-checkpoint-postgres` 3.1.2. Its current
HITL API is dynamic `interrupt()` resumed by `Command(resume=...)`; static
`interrupt_before=` is a breakpoint facility and is not the approval protocol.

## Decision

- A LangGraph thread and an agent run are one-to-one. `thread_id` is `str(agent_run_id)`.
- Checkpoint state contains only minimal JSON-compatible snapshots. Runtime dependencies, ORM
  objects and mutable `PendingApproval` instances are reconstructed after a restart.
- `execute_action` calls `interrupt()` before any I/O. The future API authenticates the user,
  verifies the persisted pending interrupt with `aget_state()`, and sends a validated decision in
  `Command(resume=...)`. The node calls `DecideApproval`; the API does not execute the task.
- `action_id` and `task_id` are generated before the interrupt and persisted in graph state. The
  database enforces one final action and one approval per action. Task, AgentAction and Approval
  share one SQLAlchemy transaction; an identical retry returns the stored result and a conflicting
  decision is rejected.
- `agent_runs` is an immutable run root written before graph execution. Append-only
  `agent_run_events` rows record interrupt, resume, completion and failure. Terminal events repeat
  graph/prompt/model configuration and carry actual latency, tokens, cost and error so one terminal
  event is independently reproducible.
- `graph_version` is `account-prioritization.v1`; `prompt_version` is
  `prioritize_accounts.v1`. The prompt is a versioned file.
- The LLM port returns a typed result envelope with model configuration and usage. At most three
  total attempts are made for invalid structured output.
- The task owner is injected from the authenticated requesting actor. A proposed due date must be
  in the future and at most 30 days away. Context budget is configurable and defaults to 4096
  estimated tokens.
- Runtime composition owns an `AsyncConnectionPool` and one compiled graph for its lifespan.
  `AsyncPostgresSaver.setup()` owns checkpoint schema setup; Alembic continues to ignore those
  third-party tables.
- Checkpoint deserialization uses strict JSON/msgpack allowlists and never enables pickle fallback.

## Consequences

The graph can resume safely after process loss and after a crash between the business commit and
the next LangGraph checkpoint. The price is an application contract change, a second migration,
an additional append-only event table, and explicit reconciliation of a duplicate resume. These
changes intentionally expand Item 5 beyond `infrastructure/agent/`; keeping the old scope would
leave the acceptance criteria unverifiable.

This ADR completes ADR-0002's temporary `run_id` decision: existing orphan actions receive an
explicit synthetic legacy run during migration, then `agent_actions.run_id` becomes non-null.
