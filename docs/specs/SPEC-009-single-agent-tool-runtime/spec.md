# SPEC-009: Bounded Single-Agent Tool Runtime

- **Status:** done
- **Owner:** Product owner and platform engineering
- **Roadmap phase:** 2-3
- **Created:** 2026-10-05

## Problem

The current agent graph executes one fixed prioritization sequence. It cannot route a request to the
small set of already-approved CRM capabilities, enforce a per-run tool budget, or record a
reproducible sequence of tool calls before returning to the existing approval/checkpoint flow. This
leaves the platform short of the guide's conditional routing, explicit tool catalog, and bounded
single-agent runtime requirements.

The first runtime must improve capability without introducing a multi-agent system, external
integrations, or a broad public API. It must remain safe when the request, retrieved context, or
model output is ambiguous or malicious.

## User stories

- As a RevOps user, I want one agent to choose among the approved CRM read and task capabilities,
  so that a request reaches the correct bounded workflow instead of always following the same path.
- As a platform operator, I want every tool call to have a schema, allowlist entry, risk level and
  audit evidence, so that runtime behavior is reproducible and reviewable.
- As a security owner, I want untrusted request and context content to remain data, so that it
  cannot select unauthorized tools, change tenant scope, or bypass approval.
- As a maintainer, I want a small deterministic tool budget and checkpointed resume behavior, so
  that retries cannot create unbounded work or duplicate a write.

## In scope

- Replace the fixed internal graph routing boundary with a bounded single-agent dispatcher while
  preserving the existing authenticated agent-run and approval endpoints.
- Route only these initial request outcomes: account/context read, account prioritization analysis,
  and a proposed task action. Unsupported or ambiguous requests fail closed with a typed runtime
  outcome and no side effect.
- Use the existing allowlisted tools only: `search_accounts`, `get_account_context`, and
  `create_task`. No new external integration is introduced by this spec.
- Validate every model-produced tool name and argument payload with a Pydantic schema, then apply
  domain policy, tenant authorization, and risk classification before execution.
- Enforce a maximum of five tool calls per run and at most one write side effect per run.
- Require the existing approval checkpoint before the `create_task` write and resume the same
  checkpointed run without duplicating the write.
- Record append-only run/tool evidence using the existing agent-run and audit boundaries, including
  tool name, risk, sequence, outcome, and sanitized metadata.
- Add deterministic offline runtime/tool-selection evaluation and adversarial coverage for tool
  confusion, tenant override attempts, prompt injection, invalid arguments, budget exhaustion, and
  approval replay.

## Out of scope

- New public HTTP endpoints, request/response contracts, UI or SSE changes.
- Email, calendar, CRM update, bulk action, research, enrichment, MCP, or other external tools.
- New Python or JavaScript dependencies, credentials, providers, or MCP servers.
- New database tables, destructive migrations, mutable memory stores, or changes to existing tenant
  ownership boundaries.
- Multi-agent orchestration, specialist agents, delegation, or a supervisor graph.
- Automatic execution of medium/high-risk writes without HITL.
- Hybrid retrieval, reranking, grounded generation, or changes to SPEC-008 retrieval semantics.

## Acceptance criteria

1. Given an authenticated request in one of the three supported outcomes, when the runtime routes
   it, then it selects only an existing allowlisted tool and records the selected route without
   changing the existing public agent-run response contract.
2. Given a model-produced tool name or arguments that are unknown, malformed, cross-tenant, or
   outside the tool schema, when dispatch is attempted, then the runtime returns a typed failure,
   records a sanitized failure event, and performs no tool side effect.
3. Given a run with repeated tool selections, when the fifth tool call completes, then a sixth call
   is rejected with a deterministic budget failure and no sixth tool is invoked.
4. Given a run that reaches `create_task`, when the proposal is produced, then the run pauses at the
   existing approval checkpoint and no task write occurs before approval.
5. Given an approved `create_task` proposal, when the checkpoint is resumed once or replayed with
   the same decision, then at most one task is created and the append-only audit evidence identifies
   the same run, action, risk and idempotency boundary.
6. Given a rejected or edited proposal, when the checkpoint resumes, then the runtime performs only
   the approved decision, records the decision, and never executes the original unapproved payload.
7. Given untrusted request, retrieved, or tool-output text containing instructions to change policy,
   tenant identity, tool allowlists, or approval state, when routing or dispatch runs, then the text
   remains data and cannot alter authorization, risk, routing constraints, or HITL behavior.
8. Given an unsupported or ambiguous request, when routing runs, then the runtime fails closed with
   a stable outcome, records no external write, and does not guess a new product capability.
9. Given the offline runtime contract dataset, when the deterministic eval suite runs without
   credentials or network, then routing, allowlist, schema, budget, HITL, replay, tenant and
   fencing cases score 1.00; live provider behavior is not required by CI.
10. Given the existing unit, integration, adversarial, architecture and offline eval suites, when
    the feature is verified, then no existing threshold, tenant boundary, audit invariant, or
    public agent-run contract regresses.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `search_accounts` | read | low | no |
| `get_account_context` | read | low | no |
| `create_task` | write | medium | yes |

The dispatcher itself is not an additional business tool. Unknown tools are denied by default.

## Data model impact

No new tables or migrations are planned. Reuse the existing checkpoint state, `agent_runs`,
`agent_run_events`, approvals, audit trail and idempotency boundaries. Any new state fields must be
backward-compatible, serializable checkpoint snapshots and tenant-scoped. Existing append-only
records must not be updated in place or deleted.

## Security considerations

The request, retrieved passages and tool outputs are untrusted data. They must be fenced and must
never supply tenant identity, tool permissions, risk levels or approval decisions. Tool execution
must follow schema validation, domain rules, tenant authorization, risk classification and HITL in
that order. The runtime must deny by default, redact secrets/PII from evidence, preserve audit
append-only behavior, and enforce the five-call/one-write bounds. Adversarial tests must attempt
prompt injection, cross-tenant selection, invalid schemas, tool-name confusion, budget bypass and
approval replay.

## Eval impact

Add a deterministic `agent_tool_runtime_contract` dataset/scorer using synthetic requests and
scripted model outputs. It must remain separate from generation quality and require no provider
credentials or network. The mandatory threshold is exact contract match `1.00`; any failure in
allowlist enforcement, schema validation, tenant isolation, budget, HITL, replay idempotency or
untrusted-data fencing is a regression. Extend the adversarial suite with the runtime cases listed
above and preserve the existing retrieval/ingestion eval baselines.

## Risks and open questions

- The dispatcher could accidentally turn a read-only request into a write; the one-write rule,
  explicit tool registry and approval checkpoint are mandatory mitigations.
- A model may repeatedly choose the same tool; the hard five-call limit must be enforced outside the
  model output.
- Existing graph state and event schemas must remain compatible with checkpoint resume; a migration
  is not acceptable as an implementation shortcut.
- The exact internal route names and event metadata keys belong in `plan.md` only after this spec is
  agreed; they must not become a new public API contract.
- The platform owner must confirm whether ambiguous requests should return a structured refusal only
  or also include a user-facing clarification prompt. The safe default is refusal without a side
  effect.

---

The scope and acceptance criteria were agreed on 2026-10-06. Implementation remains blocked until
the `plan.md` is reviewed and agreed.
