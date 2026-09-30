# ADR-0013: Classify knowledge retries and journal processing attempts

- **Status:** accepted
- **Date:** 2026-09-30
- **Context spec:** SPEC-007

## Context

Knowledge processing runs with at-least-once Celery delivery. A worker can fail after confirmation,
during embedding, or after publication commits but before the broker receives an acknowledgement.
The existing lifecycle marked every exception as terminal immediately, which made a later Celery
retry incompatible with the persisted `failed` state. Reusing `agent_actions` would also require a
fake agent run for work that is not an agent execution.

## Decision

Keep the broker payload limited to `corpus_id` and `version_id`. The application processing use
case derives the publication actor from the immutable confirmed version and accepts delivery
metadata only for audit idempotency.

Classify failures with sanitized codes. Embedding adapters expose whether a provider failure is
retryable; the worker separately classifies transient persistence failures. The provider retains
its two bounded request retries, while Celery performs at most two whole-job retries with bounded
backoff. Deterministic contract, lifecycle, payload, and programming failures are terminal.

Store every processing attempt in append-only `knowledge_processing_events`. A deterministic event
identity covers the delivery, attempt, and event type. The journal stores identifiers, attempt,
event type, retryability, a sanitized failure code, and timestamp, but never content, vectors,
credentials, or raw exception messages. A success event commits atomically with the ready status,
embedding provenance, chunks, corpus revision, activation, and head update. A terminal failure
event commits atomically with the failed status.

Confirmation replay republishes confirmed or processing versions. Processing a ready version is an
idempotent success, so broker redelivery after a lost acknowledgement cannot duplicate publication.

## Rejected alternatives

- Retrying every exception up to five times increases cost and can hide deterministic defects.
- Provider-only retries cannot recover transient database failures or a lost worker process.
- Status plus logs lacks a durable append-only history of attempts and terminal outcomes.
- Reusing `agent_actions` couples a background ingestion job to an unrelated agent-run lifecycle.
- A distributed processing lease adds expiry and heartbeat failure modes without improving the
  atomic publication invariant; duplicate computation is bounded and persistence remains idempotent.
