# SPEC-009: Bounded Single-Agent Tool Runtime Plan

## Approach

Replace the fixed internal account-prioritization path with a bounded dispatcher inside the
existing LangGraph runtime. The dispatcher consumes a structured model decision, validates the
requested outcome and tool call, applies the existing domain allowlist and risk policy, resolves
the authenticated tenant from graph state, and invokes only typed internal tool adapters. The
public `/agent/runs` start, stream, and approval response contracts remain unchanged.

The first implementation stays single-agent and synchronous from the graph's point of view. Reads
may consume multiple calls up to the hard budget of five. `create_task` produces the existing
pending approval snapshot and interrupts before any write. Approval resume continues the same
checkpointed thread and relies on the existing action/approval idempotency boundary; a replay must
not create a second task.

Unsupported or ambiguous requests, unknown tools, malformed arguments, tenant mismatches, budget
exhaustion, and policy violations are typed terminal outcomes. They are recorded as sanitized
append-only events and never fall through to the old prioritization or a guessed capability.

## Layers and responsibilities

### Domain

- Extend the pure tool policy boundary under `packages/core/revops/domain/` with supported runtime
  outcomes, bounded call/write counters, and deterministic failure codes for deny-by-default.
- Reuse `RiskLevel`, `classify`, and `requires_hitl`; do not duplicate the tool risk matrix in an
  adapter or prompt.
- Keep the domain independent of Pydantic, LangGraph, SQLAlchemy, FastAPI, LLM clients, and audit
  persistence.

### Application

- Add strict Pydantic DTOs for the three supported outcomes, model-produced tool calls, typed
  runtime failures, sanitized tool evidence, and the internal runtime result. All model payloads
  use `extra="forbid"`; organization and actor identity come from trusted run context.
- Add application ports for typed adapters for `search_accounts`, `get_account_context`, and
  `create_task`, plus the bounded dispatcher if needed. Ports expose no SQLAlchemy sessions or
  public HTTP contracts.
- Implement the dispatcher/use case that validates outcome, tool name, arguments, tenant scope,
  risk, call budget, and one-write budget in that order. The budget is enforced by application
  state, never by a prompt instruction alone.
- Map existing `PrioritizeAccounts`, account repositories, `ProposeTask`, and `DecideApproval`
  behavior behind typed adapters rather than duplicating business rules. `create_task` stops at
  the existing approval boundary and resumes with the persisted action identity.
- Define stable internal evidence keys for route, sequence, tool, risk, outcome, failure code, and
  sanitized arguments/results. These are internal evidence, not a new public API.

### Infrastructure

- Adapt existing account and task persistence/use-case composition to the application tool ports.
  Tenant filtering uses authenticated organization identity, never model-produced fields.
- Update LangGraph state and graph composition to carry the serialized runtime decision, counters,
  tool evidence, typed pending approval, and terminal outcome through checkpoint snapshots.
- Replace the fixed routing boundary with the dispatcher while preserving `interrupt()` before I/O
  and `Command(resume=...)`. No new checkpointer or database table is allowed.
- Extend `AgentGraphRunner` lifecycle journaling to append route/tool/failure evidence without raw
  model output, secrets, or unredacted PII in metadata.
- Keep graph and prompt versions explicit; bump prompt version if the structured model contract
  changes, retaining the runner's model configuration evidence.

### Apps and composition roots

- Wire the dispatcher and typed adapters in `apps/api/runtime.py` as an internal composition
  concern. Existing authenticated agent-run routes remain the only public entry points.
- Preserve organization authorization in `apps/api/routes/agent_runs.py`; add no request-body
  organization, corpus, tool permission, risk, or approval fields.
- Do not change the web app, SSE contract, migrations, external providers, credentials, or MCP
  surface.

## Internal contracts

The exact DTO names may change during implementation, but these boundaries are fixed:

```python
class AgentTool(Protocol):
    name: ClassVar[str]
    risk: ClassVar[RiskLevel]

    async def execute(
        self, *, organization_id: UUID, actor_id: UUID, arguments: BaseModel
    ) -> ToolExecutionResult: ...


class AgentToolRuntime(Protocol):
    async def run(
        self, *, context: TrustedRunContext, request_text: str
    ) -> RuntimeResult: ...
```

The runtime may use narrower ports if that better matches current application style. A tool adapter
never accepts organization identity, risk, allowlist, approval, or idempotency decisions from model
output. The runtime owns those values.

## Routing and execution rules

1. Normalize only the trusted request envelope; request text remains untrusted data.
2. Ask the configured structured-output gateway for a runtime decision using a versioned prompt and
   fenced request/context sections.
3. Validate the decision schema and supported outcome. Unknown or ambiguous outcomes return the
   stable refusal result without a tool call.
4. Resolve the tool from the domain allowlist. Unknown names fail closed.
5. Validate tool-specific Pydantic arguments with `extra="forbid"`; reject tenant/authorization
   fields supplied by the model.
6. Apply tenant authorization and domain risk classification before any adapter call.
7. Reject calls after the fifth completed/attempted call using one deterministic counter; reject a
   second write before invocation.
8. Execute reads through typed adapters and append sanitized evidence after each result.
9. For `create_task`, build the existing proposal/action snapshot, interrupt before persistence,
   and on resume execute only the approved or edited payload through `DecideApproval`.
10. On every refusal or failure append a typed, sanitized event and finish without a side effect.

## Checkpoint, audit, and replay strategy

- Reuse `AgentGraphState`, the Postgres checkpointer, `AgentRunJournal`, `AgentAction`, `Approval`,
  and the append-only audit repository. Add only backward-compatible JSON-serializable state.
- Derive one deterministic action/idempotency identity from the run and runtime action, preserving
  the current `uuid5` action identity convention. Do not create a task before approval.
- On resume, validate the persisted proposal and decision against authenticated tenant and action
  identity before calling the existing approval use case.
- A repeated identical approval returns the existing result or deterministic replay outcome; a
  conflicting decision fails closed. No audit/event row is updated or deleted.

## Test plan

### Unit tests

- Domain tests for supported outcomes, tool registry/risk lookup, call/write counters, stable
  failure codes, and deny-by-default behavior.
- Application tests for strict schemas, tenant injection, tool selection, unknown/malformed calls,
  budget exhaustion, one-write enforcement, sanitized evidence, unsupported/ambiguous refusal, and
  read adapter invocation.
- Approval tests for proposal, approve/edit/reject, same-thread resume, identical replay,
  conflicting replay, and no write before interrupt.
- State serialization tests for backward-compatible checkpoint snapshots and deterministic metadata.

### Integration tests

- Run authenticated start/stream/approval API tests with existing public response shapes.
- Verify account reads are tenant-scoped and task creation uses existing approval/action/audit rows
  exactly once.
- Restart/resume a real Postgres checkpoint and verify repeated approval cannot create a second task.
- Verify unsupported, cross-tenant, invalid-schema, and budget failures persist sanitized lifecycle
  evidence and no side effects.

### Adversarial tests

- Attempt prompt injection through request, retrieved context, and tool output to change tool
  allowlists, tenant identity, risk, or approval state.
- Attempt unknown tools, tool-name confusion, extra fields, caller-selected organization IDs,
  write-before-approval, bulk/multi-write, sixth-call, and replay payloads.
- Assert raw model output, secrets, and PII do not enter events or audit payloads.

## Eval plan

- Add `evals/datasets/agent_tool_runtime_contract.jsonl` and a deterministic scorer registered in
  `evals/run.py` and `evals/thresholds.toml`.
- Cover all three supported outcomes plus refusal, allowlist/schema enforcement, tenant isolation,
  five-call budget, one-write budget, HITL pause, approve/edit/reject, replay, and data fencing.
- Use scripted structured decisions and synthetic data only. The suite must run at exact score
  `1.00` without credentials, network, or live model calls.
- Keep the existing `tool_selection` baseline until the new runtime suite proves equivalent or
  stronger coverage; do not silently change its threshold.

## Documentation and rollout

1. Add an ADR only if implementation selects a state/event shape not already justified by the
   existing LangGraph HITL ADR; otherwise record bounded choices in this plan and traceability.
2. Implement domain/application contracts and unit tests.
3. Implement typed adapters, graph state/routing, checkpoint resume, and lifecycle evidence.
4. Add integration/adversarial tests and the deterministic runtime eval.
5. Wire the API composition root and verify public contracts remain unchanged.
6. Update PDF traceability, security evidence, task checkboxes, and handoff state.
7. Run the full verification gate. Only after all tasks and the bounded pilot are green may the
   autonomous queue be created; an overnight loop is not part of this implementation phase.

## Trade-offs

- Keep routing inside the existing graph rather than adding a public endpoint, preserving API
  contract and checkpoint ownership.
- Use a typed registry plus explicit adapters instead of provider-native function calling, because
  provider output remains untrusted until schema, policy, tenant, risk, and HITL checks pass.
- Use refusal rather than clarification for ambiguous requests in this bounded runtime. A
  clarification UX can be specified separately without guessing a capability here.
- Reuse existing audit/checkpoint tables rather than adding runtime tables, honoring the no-migration
  constraint and append-only evidence boundary.
