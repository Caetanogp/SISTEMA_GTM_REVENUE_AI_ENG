# SPEC-006: Auditable Multi-Provider LLM Gateway

- **Status:** agreed
- **Owner:** Caetano
- **Roadmap phase:** 1/3 - Code-first MVP and production AI engineering foundation
- **Created:** 2026-09-13

## Problem

The agent currently exposes only an unconfigured LLM boundary and a deterministic fake. The
platform guide requires a provider gateway that supports OpenAI and Anthropic, routing, fallback,
cost metadata, latency metadata and reproducible model configuration. Without that boundary, the
vertical slice cannot run against a real provider safely or explain which provider produced a run.

## User stories

- As a RevOps engineer, I want one structured gateway contract for OpenAI and Anthropic, so that
  application use cases do not depend on provider SDKs or wire formats.
- As an operator, I want bounded retries and a controlled fallback, so that transient provider
  failures do not unnecessarily stop a run or silently bypass safety decisions.
- As a product owner, I want each run to record the requested and actual model, route policy,
  pricing catalog, usage and latency, so that a result is auditable and reproducible.
- As a user, I want English and Portuguese requests to preserve the requested language in textual
  model-authored fields while keeping structured field names and enums stable.

## In scope

- A first-party infrastructure gateway implemented over the existing `httpx` dependency.
- OpenAI Responses API and Anthropic Messages API adapters with strict JSON Schema output.
- Configuration-driven ordered routing with OpenAI primary and Anthropic fallback by default.
- Explicit `disabled` and `live` modes, strict live configuration validation and secret-safe settings.
- Bounded transport retries, exponential backoff with jitter, retry-after limits and a total deadline.
- Fallback only for recoverable transport, timeout, rate-limit and server failures.
- Passive in-memory provider health snapshots and a sanitized `GET /health/llm` endpoint.
- Versioned model pricing with Decimal calculations and rejection of unknown live models.
- Explicit `agent_runs.thread_id`, actual provider metadata and terminal latency/cost usage.
- Append-only durable run journaling so failed provider calls remain auditable.
- Prompt version `prioritize_accounts.v2` for English and Portuguese textual output.
- Mandatory offline gateway contract evals and an optional, never-CI live smoke command.

## Out of scope

- RAG, embeddings, pgvector, knowledge ingestion, retrieval or long-term memory (SPEC-007/008).
- Provider tools, web search, file search, function calling or model-generated side effects.
- Task-based model selection or user-controlled provider/model selection.
- Production circuit breakers, coordinated rate limits, DLQ and external-operation reconciliation
  (SPEC-019).
- LangSmith, OpenTelemetry, Sentry dashboards and full operational metrics (SPEC-014).
- Multi-agent routing, autonomous actions, UI, MCP and external CRM connectors.
- Image/container/Git/RAG/eval/schema version registry completion beyond the model-gateway slice.

## Acceptance criteria

1. Given default local settings and no provider credentials, when the API starts, then it remains
   offline, performs no provider call and the existing fake injection tests remain green.
2. Given live mode and a configured provider route, when a structured completion is requested, then
   the selected adapter sends strict JSON Schema output and returns a validated Pydantic result.
3. Given the OpenAI adapter, when the request completes, then it uses `store=false` and records the
   requested/resolved model, token usage, Decimal cost, latency and gateway configuration.
4. Given the Anthropic adapter, when the request completes, then it uses structured output and
   records equivalent provider-neutral usage and configuration metadata.
5. Given a transient primary-provider failure, when bounded retries are exhausted, then the
   configured fallback is attempted; non-transient, configuration and safety failures do not fall
   back.
6. Given a configured live model absent from the versioned price catalog, when the gateway is
   built, then configuration fails before any external request is made.
7. Given a provider response containing invalid or untrusted content, when it crosses the gateway,
   then schema validation occurs before application use and no invalid action can execute.
8. Given a health request, when no active probe is requested, then `GET /health/llm` returns only
   sanitized aggregate/provider state and never exposes secrets, prompts, responses or raw errors.
9. Given an agent run, when it starts and reaches any terminal state, then its explicit thread,
   route/version configuration and terminal provider, latency, token, cost or sanitized failure
   event are durably recorded without updating append-only audit rows.
10. Given English and Portuguese requests, when the offline gateway contract suite runs, then both
    language cases preserve the prompt and structured contract while meeting the exact eval gate.
11. Given live credentials and explicit confirmation, when the optional live smoke command runs,
    then it can exercise both providers without being part of CI or the merge gate.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| OpenAI Responses API | external generation | medium | no |
| Anthropic Messages API | external generation | medium | no |
| `GET /health/llm` | read-only diagnostic | low | no |

No provider tool call may create or modify CRM state. Existing HITL rules remain authoritative for
all business writes.

## Data model impact

Add a backward-compatible `thread_id` column to `agent_runs`, backfill it from the existing
one-to-one run/thread identity, then enforce non-null and uniqueness. Add no business entities or
provider-specific tables. Terminal provider facts remain in append-only `agent_run_events`.

## Security considerations

- Provider keys are loaded as secret settings, never committed, logged or returned by diagnostics.
- OpenAI requests explicitly disable application state storage; provider responses and raw error
  bodies are not persisted.
- External model content remains untrusted and must pass Pydantic schema, domain policy,
  authorization and risk checks before any side effect.
- Safety refusals, authentication failures and billing failures never trigger cross-provider
  fallback, preventing policy or account errors from being hidden.
- Offline and live smoke commands must not print prompts, completions, credentials or PII.

## Eval impact

Add a deterministic `llm_gateway_contract` suite covering English, Portuguese, route selection,
retry/fallback boundaries, schema rejection and pricing validation. The suite is mandatory and has
an exact-match threshold of `1.00`. Existing `tool_selection` and `lead_scoring` suites must remain
green. Live provider smoke checks are opt-in and never run in CI.

## Risks and open questions

- Provider response schemas and model prices change, so adapters and the versioned catalog must be
  reviewed together.
- A timeout after provider-side processing can make the cost of that attempt unknowable; the event
  must represent unknown cost rather than zero.
- The in-memory health snapshot resets on process restart; durable health and circuit breakers are
  intentionally deferred to the reliability spec.
- Model defaults are `gpt-5.6-terra` and `claude-sonnet-5`, with environment overrides restricted
  to cataloged models.
