# SPEC-004 implementation plan: core agent tool runtime

## Approach

Keep the runtime single-tool and deterministic at the execution boundary. A request is converted to
one validated tool-selection/result envelope, then the application use case resolves tenant data or
creates a task proposal. No model output is allowed to call infrastructure directly.

## Layers touched

### Domain

- Extend the risk registry for the five catalog names, preserving deny-by-default and `create_task`
  as medium risk.
- Add only pure value objects or policy helpers needed for tool names, result outcomes, filters, and
  bounded limits. No framework, database, network, or prompt imports.

### Application

- Add strict Pydantic argument/result DTOs for each tool and a common `ToolOutcome` envelope with
  `completed`, `clarification`, `unsupported`, and validation-error states.
- Add a catalog/selection contract and a single-tool execution use case.
- Add ports for tenant-scoped account context and pipeline snapshot reads if existing repository
  ports cannot express the required queries; keep the existing task and unit-of-work contracts.
- Keep identity, authorization, canonical resolution, risk classification, audit, and HITL decisions
  outside model-generated payloads.

### Infrastructure

- Implement repositories/adapters for the read ports using existing SQLAlchemy models and canonical
  resolution. Apply limits in the query and in the application boundary.
- Implement an OpenAI Responses API `LLMGateway` adapter using structured output, explicit model and
  timeout/retry settings, `store=false`, and usage metadata. No network calls in unit tests.
- Add versioned tool-routing and tool-specific prompt files with prompt-version metadata.
- Adapt the graph runner so one run routes to one tool and emits the typed result through persisted
  events without breaking the existing approval checkpoint.

### Apps/API

- Extend the existing `POST /agent/runs`, list, stream, and approval response models additively for
  typed tool outcomes and clarification/unsupported states.
- Wire the configured gateway and adapters at the composition root. Do not add business logic to
  routers or create direct tool endpoints.

## Contracts

- `ToolCatalog`: returns immutable metadata for the five allowlisted tools, argument schema, result
  schema, risk, and HITL requirement.
- `ToolExecutor.execute(organization_id, actor_id, run_id, tool_name, arguments)`: validates the
  catalog entry and returns a typed outcome; the organization and actor are not arguments from the
  LLM.
- `AccountQueryRepository`: tenant-scoped practical search and canonical account context.
- `PipelineMetricsRepository`: tenant-scoped current stage snapshot with an optional canonical
  account filter.
- Existing `TaskRepository`, `AuditTrail`, `ApprovalRepository`, `CanonicalResolver`, and
  `LLMGateway` remain the seams for writes, audit, identity, and model calls.

## Data and migration strategy

Use existing tables and event metadata first. If typed results need persistence beyond JSON metadata,
add nullable/backward-compatible columns or a versioned result payload in a separate migration. Run
upgrade, downgrade, and upgrade against Docker PostgreSQL. Never store raw secrets or unnecessary
prompt/CRM PII.

## Trade-offs

- **Single tool per run over tool chaining:** chosen to bound side effects, latency, and review scope;
  multi-tool orchestration needs measured evidence in a later spec.
- **Existing agent-run surface over new tool endpoints:** preserves one audit/stream/approval path and
  avoids duplicating authorization logic.
- **OpenAI adapter behind the existing gateway over provider-specific application code:** keeps the
  application layer provider-neutral and makes fake-gateway tests deterministic.
- **Structured clarification over free-form fallback:** avoids guessing and makes unsupported intent
  observable and testable.
- **Current pipeline snapshot over temporal analytics:** matches the agreed MVP and avoids inventing
  reporting semantics before a dedicated analytics spec.
- **Offline eval gate with optional live smoke:** keeps CI reproducible while allowing provider checks
  when credentials and network are deliberately available.

## Test plan

- Unit: DTO strictness, filters and limits, tool catalog/allowlist, risk and HITL policy, language
  cases, canonical/tenant boundaries, clarification/unsupported outcomes, and fake gateway behavior.
- Integration: each read tool through `POST /agent/runs` and SSE, canonical account context, pipeline
  snapshot, structured draft, and create-task approval/resume against Docker PostgreSQL.
- Adversarial: prompt injection in CRM fields, cross-tenant IDs, unknown tool selection, malformed
  structured output, over-limit requests, and write attempts without approval.
- Architecture: `lint-imports` and import-boundary tests must remain green.

## Eval plan

Add cases for all five tools in English and Portuguese, at least three clarification/unsupported
requests, over-limit and cross-tenant negatives, and explicit `create_task` approval behavior. The
offline suite is a required gate with thresholds recorded beside the dataset/scorer. Optional live
evals use synthetic data, `store=false`, and never mutate CRM state.

## Rollout

Implement behind the existing configured gateway with the fake gateway as the default test path.
Verify the full playbook before merge. Do not launch an unattended development loop until the spec,
plan, tasks, implementation, and verification gate are complete and the queue is regenerated from
the final tasks.
