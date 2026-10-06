# ADR-0017: Bounded single-agent tool runtime

- **Status:** accepted
- **Date:** 2026-10-06
- **Scope:** SPEC-009

## Context

The existing LangGraph runtime follows one fixed account-prioritization path. SPEC-009 needs
conditional routing across three already-approved CRM capabilities without introducing a public API,
new provider integration, a second checkpoint system, or a multi-agent supervisor.

Model output is untrusted. It cannot choose tenant identity, permissions, risk, approval state, or
an arbitrary tool. The runtime also needs deterministic bounds and must preserve the current
append-only run/audit and HITL checkpoint behavior.

## Decision

- Route through one application-owned dispatcher inside the existing LangGraph graph.
- Keep exactly three outcome/tool pairs: account context read with `get_account_context`, account
  prioritization with `search_accounts`, and proposed task action with `create_task`.
- Validate structured model output with strict Pydantic schemas, then apply the domain allowlist,
  tenant authorization, risk classification, call budget, and write budget before adapter calls.
- Enforce at most five tool calls and one write per run in runtime-owned checkpoint state, not in
  prompts or model instructions.
- Reuse the existing `interrupt()`/`Command(resume=...)` checkpoint and `DecideApproval` use case.
  `create_task` produces a proposal only; no task write occurs before approval.
- Reuse existing `agent_runs`, `agent_run_events`, `agent_actions`, `approvals`, and idempotency
  boundaries. Add no tables or migrations.
- Record only sanitized route/tool/failure evidence in lifecycle events. Raw model output, secrets,
  PII, and tool payloads do not enter runtime evidence.
- Refuse unsupported or ambiguous requests with a stable typed outcome and no side effect. A
  clarification user experience is deferred to a separate scoped change.

## Rejected alternatives

- **Provider-native tool calling:** rejected because provider output would still need the same local
  schema, policy, tenant, risk, and HITL checks, while coupling the contract to a provider.
- **New public runtime endpoint:** rejected because the existing authenticated agent-run contract
  already owns authorization, streaming, and approval resume.
- **New runtime tables:** rejected because checkpoint JSON plus existing append-only rows provide the
  required evidence without a migration.
- **Automatic clarification or guessed capability:** rejected because ambiguity must fail closed in
  the first bounded runtime.

## Consequences

The runtime remains intentionally small and single-agent. Read capabilities can be expanded only by
adding a reviewed tool schema, domain allowlist entry, adapter, unit test, and eval case. A future
clarification UX or multi-agent design requires a new spec and separate acceptance criteria.
