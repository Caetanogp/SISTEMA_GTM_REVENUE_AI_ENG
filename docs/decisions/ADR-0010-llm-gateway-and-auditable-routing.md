# ADR-0010: Provider-neutral LLM gateway and auditable routing

## Status

Accepted for SPEC-006.

## Decision

Use a first-party provider-neutral gateway over HTTPX. The gateway exposes one structured
application port and keeps provider wire formats, model routes, retry classification, fallback,
health and Decimal pricing in infrastructure.

Live mode is explicit and disabled by default. The configured route is ordered and may fall back
only after bounded recoverable transport, timeout, rate-limit or server failures. Authentication,
permission, billing, invalid-request, safety-refusal and schema failures never cross-provider
fallback.

Every successful or failed run records a sanitized configuration and terminal event. The run has an
explicit LangGraph `thread_id`; the journal commits independently from business unit-of-work
transactions. OpenAI requests set `store=false`, and no provider tools or generated side effects
are enabled by this gateway.

## Consequences

The application remains independent of provider SDKs and can use the deterministic fake in local
tests. The catalog must be updated with adapter changes when provider models or prices change.
Passive health is process-local; coordinated circuit breakers and operational telemetry remain
owned by later specs.

## Evidence

- `packages/core/revops/infrastructure/llm/gateway.py`
- `packages/core/revops/infrastructure/llm/providers.py`
- `packages/core/revops/infrastructure/persistence/repositories.py`
- `tests/unit/infrastructure/llm/test_gateway.py`
- `python -m evals.run --suite all`
