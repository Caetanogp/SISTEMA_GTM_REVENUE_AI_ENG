# SPEC-006 implementation plan

## Approach

Build a thin provider-neutral gateway in infrastructure over `httpx`, with one adapter for the
OpenAI Responses API and one for the Anthropic Messages API. The application keeps one structured
`LLMGateway` port and receives immutable configuration and usage snapshots; provider wire formats,
retry classification and cost calculation remain outside the application layer.

The gateway is disabled by default. In live mode, a strict composition validator builds only a
fully configured, cataloged route. The default route is OpenAI followed by Anthropic, while the
fallback order and model IDs remain environment configuration, never request input.

## Layers touched

- Application: typed gateway configuration, health and failure contracts; preserve the existing
  structured result port and bounded schema retry.
- Infrastructure: HTTPX provider adapters, route executor, retry policy, health state, pricing
  catalog and provider-neutral usage metadata.
- API: settings wiring, lifecycle cleanup and sanitized `/health/llm` response.
- Persistence: explicit `thread_id` migration and an append-only run journal that commits lifecycle
  events independently from business transactions.
- Prompts/evals/docs: bilingual prompt version, offline contract suite, optional live smoke and PDF
  traceability evidence.

## Contracts and policies

- `LLMGateway.complete(prompt, response_model)` remains the only application completion call.
- Add synchronous configuration and passive health snapshots without exposing secrets.
- Use strict JSON Schema generated from the requested Pydantic model, validate the returned payload
  again locally and return only the typed model.
- Retry at most two times per provider with a 30-second attempt timeout, 90-second completion
  deadline, 0.5-second initial backoff, 8-second cap and injectable jitter in tests.
- Retry and fallback only network/timeout, 408, 409, recoverable 429, 5xx and 529 failures. Never
  fallback authentication, permission, billing, invalid request, safety refusal or schema failure.
- Record requested and resolved model IDs, provider, route policy, gateway version, pricing version,
  attempt summaries, fallback usage, token breakdown, cost and latency.
- Use `store=false` for OpenAI and no provider-side tools or conversation state.

## Persistence and migration

Add `thread_id VARCHAR(128)` to `agent_runs`, backfill `str(id)` for historical rows, then enforce
non-null and uniqueness in the same backward-compatible migration. The journal writes the run root
and initial event atomically, then appends terminal events in independent transactions. Existing
business unit-of-work boundaries remain unchanged. Failed model calls are retained as sanitized
terminal events; audit tables are never updated or deleted.

## Trade-offs

- Use first-party HTTPX adapters instead of LiteLLM to keep the two-provider contract explicit,
  avoid a broad dependency and retain control over safety/error boundaries.
- Use ordered configured fallback instead of task-based routing because model choice is not yet
  supported by eval evidence and must not be influenced by untrusted input.
- Use passive health instead of active probes or a circuit breaker because probes cost money and
  coordinated reliability controls belong to SPEC-019.
- Use a checked-in versioned price catalog instead of nullable or environment-provided prices so
  successful usage cannot silently report fabricated cost.
- Keep final metrics in append-only terminal events rather than mutating `agent_runs`, preserving
  ADR-0003 and the audit invariant.

## Test and eval plan

- Unit-test schema payloads, response parsing, provider errors, retry classes, backoff, health,
  pricing, configuration redaction and unknown-model rejection with `httpx.MockTransport`.
- Integration-test API composition, provider fallback, terminal failure journaling, thread backfill,
  health response sanitization and existing tenant isolation.
- Add adversarial cases for injected provider error text, malicious structured fields, safety refusal
  fallback and prompt/credential leakage.
- Add mandatory deterministic English/Portuguese gateway contract cases and keep all existing offline
  eval suites unchanged.
- Add an opt-in live smoke command requiring explicit credentials and confirmation; never invoke it
  in CI or the autonomous gate.

## Rollout

Materialize this spec, plan and task checklist before code. Implement on
`feature/SPEC-006-llm-gateway`, run the full verification playbook, update traceability and handoff,
then merge into `develop` only after the gate is green. Do not push or touch `main`.
