# SPEC-004: Core agent tool runtime

- **Status:** agreed
- **Owner:** Caetano Padoin
- **Roadmap phase:** 1
- **Created:** 2026-09-12

## Problem

The agent runtime currently demonstrates one hard-coded prioritization path rather than a bounded
tool runtime. RevOps users need to ask supported account and pipeline questions through the existing
agent-run surface and receive a typed, auditable result, while write actions remain validated and
subject to the existing risk and approval policy.

## User stories

- As a `rep`, I want to ask account and pipeline questions in English or Portuguese, so that I can
  retrieve useful CRM information without knowing internal tool names.
- As a `rep`, I want a structured follow-up draft, so that I can review it before using it elsewhere.
- As an `admin`, I want the same runtime to expose the approved tool catalog, so that operational
  actions remain allowlisted, tenant-scoped, and auditable.
- As a `rep`, I want ambiguous or unsupported requests to return a structured explanation, so that
  the system does not guess or execute an unintended action.

## In scope

- A single-tool-per-run runtime behind the existing `POST /agent/runs` and SSE stream contracts.
- The five-tool catalog: `search_accounts`, `get_account_context`, `get_pipeline_metrics`,
  `prepare_followup`, and `create_task`.
- Structured Pydantic arguments and results with `extra="forbid"`; organization and actor identity
  come from authenticated run state, never from model-generated arguments.
- Practical search filters, a default result limit of 25, and a hard maximum of 100.
- Account context containing the canonical account, contacts, up to 20 recent interactions, and
  opportunities, with canonical resolution and tenant isolation.
- Pipeline metrics as a current snapshot grouped by stage, optionally filtered to one account; no
  historical or time-series analytics.
- Email-only structured follow-up drafts; no sending or external side effect.
- `create_task` using the existing task contract, risk classification, audit trail, and HITL approval.
- A configurable OpenAI Responses API adapter with structured output, explicit model configuration,
  timeout/retry policy, and `store=false`; deterministic fake gateway coverage remains required.
- Structured `clarification` and `unsupported` outcomes without free-form fallback execution.
- English and Portuguese request handling, with language preserved in user-visible structured text.
- Mandatory offline eval coverage and an optional live eval path that cannot gate local correctness.

## Out of scope

- Reply intelligence, reply classification, sentiment analysis, or suggested replies to inbound
  messages; those belong to a later separately scoped spec.
- Sending email, scheduling meetings, campaigns, external CRM writes, MCP exposure, or frontend work.
- Multi-tool plans, tool chaining, autonomous loops over tools, or parallel tool execution.
- RAG, web research, temporal pipeline analytics, forecasting, or arbitrary SQL-like filters.
- New persistence entities or migrations unless implementation proves an existing audit/run contract
  cannot represent the result; any such change requires a spec amendment first.
- Changing the existing HITL, authorization, tenant-isolation, or deny-by-default policies.

## Acceptance criteria

1. Given an authenticated `rep` or `admin`, when a supported English or Portuguese request is sent
   to `POST /agent/runs`, then exactly one catalog tool is selected or a structured non-execution
   outcome is returned through the existing response and SSE contracts.
2. Given a request that would require two tools, when the runtime evaluates it, then it returns a
   structured `clarification` or `unsupported` outcome and executes no tool.
3. Given a request for account search, when practical filters are supplied, then the runtime applies
   them, defaults to 25 results, rejects a limit above 100, and never returns another organization’s
   records.
4. Given an account-context request, when the account exists in the caller’s organization, then the
   result contains its canonical account, contacts, at most 20 recent interactions, and opportunities;
   an inaccessible account is not disclosed.
5. Given a pipeline-metrics request, when an optional account filter is supplied, then the result is
   a current count/snapshot grouped by stage and contains no unsupported temporal analytics.
6. Given a follow-up request, when it is valid, then the result is an email-only structured draft and
   no email or other external side effect occurs.
7. Given a valid task-creation request, when the tool is selected, then its arguments pass schema,
   authorization, canonical resolution, and risk validation before the existing HITL interruption;
   no task is persisted before approval.
8. Given unknown tools, malformed arguments, prompt injection in CRM content, cross-tenant IDs, or
   unsupported requests, then the runtime fails closed with a typed error/outcome and records no
   unauthorized side effect.
9. Given an OpenAI adapter configuration, when a request is completed, then structured output is
   validated, `store=false` is sent, timeout/retry behavior is bounded, and usage/model metadata is
   recorded for reproducibility; tests run without network access through the fake gateway.
10. Given the mandatory offline eval suite, when all SPEC-004 cases run, then tool-selection,
    argument-validation, safety, language, and no-side-effect cases meet their declared thresholds;
    an optional live eval may report provider behavior but cannot weaken or replace offline gates.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `search_accounts` | internal read | low | no |
| `get_account_context` | internal read | low | no |
| `get_pipeline_metrics` | internal read | low | no |
| `prepare_followup` | internal draft | low | no |
| `create_task` | internal write | medium | yes |

The catalog is deny-by-default. Only `create_task` can create a persisted write in this spec, and it
must reuse the existing approval/resume path.

## Data model impact

Prefer the existing agent-run, event, account, contact, interaction, opportunity, and task models.
Additive fields are allowed only for typed tool-result metadata if the current event metadata cannot
carry it. No destructive migration, new external identifier, or raw prompt/PII persistence is part
of this spec. Any migration must be backward-compatible and separately verified.

## Security considerations

- Model output is untrusted: schema validation, domain policy, authorization, and risk checks happen
  in that order before any side effect.
- Organization and actor IDs are injected from authentication and cannot be supplied by the model.
- CRM content is fenced as data and cannot alter policy, tool permissions, or approval requirements.
- Results and audit metadata are tenant-scoped and redact PII where operationally unnecessary.
- OpenAI requests use `store=false`; credentials come only from configured environment settings and
  are never logged.
- Adversarial tests cover prompt injection, cross-tenant identifiers, unknown tools, malformed output,
  result-limit abuse, and attempted writes without approval.

## Eval impact

Extend the offline tool-selection dataset and scorer to cover all five tools, English/Portuguese
paraphrases, clarification/unsupported cases, argument boundaries, and the no-`create_task` negative
cases. The full offline suite remains mandatory. A live-provider smoke suite is optional, explicitly
configured, and informational unless a future spec promotes it to a gate.

## Risks and open questions

- LLM routing can select a plausible but wrong tool; structured schemas, narrow descriptions,
  deterministic authorization, and offline regression cases limit the blast radius.
- Provider latency and cost are bounded by one tool per run, request limits, timeout/retry settings,
  and recorded usage.
- Portuguese coverage may initially be less accurate than English; both languages are required for
  acceptance, while quality thresholds must be declared in the eval dataset rather than hidden in
  implementation heuristics.
- The existing run result/event contract may need an additive typed-result representation; no API
  breaking change is permitted.
