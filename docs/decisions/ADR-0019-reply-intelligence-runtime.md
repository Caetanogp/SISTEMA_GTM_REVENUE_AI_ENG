# ADR-0019: Bounded Reply Intelligence Runtime

- **Status:** accepted
- **Date:** 2026-10-10
- **Scope:** SPEC-011 Item 4 and its downstream API/evaluation items

## Decision

Reply intelligence uses a dedicated fixed-tool `reply-intelligence.v1` graph with one
low-risk `classify_reply` operation. It stores the immutable reply, reserves the
classification request and `AgentRun` atomically, executes one bounded structured
classification, and persists a sanitized typed artifact in the existing PostgreSQL
LangGraph checkpoint store. No fourth artifact table is added.

The domain owns deterministic review policy: confidence below `0.80`, ambiguity,
incompatible language, invalid evidence, missing evidence, and unknown category produce
`review_required`; `unknown` is always review-required. The fixed category-to-action mapping
and unsubscribe precedence remain authoritative. Feedback is append-only and corrections do
not perform external writes.

## Runtime and replay

The graph has fixed `select`, `reserve`, `execute`, and `complete` nodes and does not use an
LLM router. A PostgreSQL advisory lock is acquired per organization/run before checkpoint
read or advance. The lock and `AsyncPostgresSaver` share one physical connection, the lock is
non-blocking, and it is held through terminal checkpoint and journal reconciliation.

Reservation is durable with `durability="sync"`; the runner consumes it and never creates a
second root event. New threads use `str(run_id)`. Legacy `reply:{reply_id}` threads are only
accepted after complete persisted-binding validation. Terminal events use deterministic UUID5
identifiers and append-once comparison, so replays are stable and conflicting payloads fail.

If a reserved call has no durable result, the runtime returns
`checkpoint_recovery_required` and never performs a blind second inference. Completed,
failed, refused, or validated-executed states are reconciled without another model call.
Unexpected interruptions remain recoverable; unknown usage is not replaced with zero.

## Bounds and data handling

The prompt is versioned as `classify_reply.v1`; original reply text is preserved exactly and
treated as fenced untrusted data. The dedicated reply gateway uses a 1024-token output limit,
a conservative 4096-byte context estimate, a 20-second model-call timeout, and a 30-second
analysis deadline. Oversized content is refused, never truncated. Canonical compact JSON,
with a 128 KiB limit before checkpointing and at completion, is the only artifact envelope.
Only whitelisted typed metadata is persisted; raw reply text and arbitrary provider errors do
not enter journal metadata.

## Context and consequences

The platform needs bilingual reply interpretation while keeping external content untrusted,
tenant identity deterministic, and SPEC-009/010 runtimes stable. This design adds a dedicated
runtime and narrow ports, but makes transaction, checkpoint, replay, and evidence boundaries
explicit. Item 4 proves the runtime contract; later items add API, 90-case evaluation,
adversarial, restart, and traceability coverage.

## Public API contract

Item 5 uses the existing API conventions and does not create a second result model:

- `POST /replies` and `GET /replies/{reply_id}` manage the authenticated organization-scoped reply.
- `POST /replies/{reply_id}/classify` starts or replays classification.
- `GET /agent/runs/{run_id}/result` reads the typed terminal artifact.
- `POST` and `GET /agent/runs/{run_id}/reply-feedback` append and list corrections.

All mutating POST requests require the `Idempotency-Key` header. The key is not accepted in the
body or query string. Tenant identity is derived from authentication. A classification response
contains `run_id`, `status`, `replayed`, and an optional result; `status` is one of
`in_progress`, `completed`, `failed`, or `recovery_required`. Replays return the original run
identity and artifact. Result reads use the direct artifact reader and never initialize a graph,
provider, or RAG component.

## Alternatives rejected

- Mailbox integration, automatic CRM mutation, and sending: deferred because they add
  credentials or external side effects outside this analysis-only boundary.
- An LLM router or multi-agent split: unnecessary for nine deterministic categories and
  contrary to the single-agent evidence gate.
- Thread-wide context: rejected for privacy, token, and ambiguity risk.
- A shared ingestion/deduplication unit of work: rejected because it mixes transaction
  invariants and replay behavior.
- A fourth artifact table: rejected because the existing checkpoint store already provides the
  required typed, durable, immutable runtime artifact.

## Traceability

This decision covers PDF reply intelligence and structured next-action behavior (PDF-02-010),
feedback linkage (PDF-05-008), measurable reply metrics (PDF-10-002), and synthetic reply data
(PDF-10-003).
