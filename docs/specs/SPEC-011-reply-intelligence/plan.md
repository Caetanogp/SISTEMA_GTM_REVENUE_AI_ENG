# SPEC-011: Reply Intelligence Implementation Plan

## Approved architecture

Implement the reply runtime inside-out while preserving the SPEC-009 and SPEC-010
composition roots. The new runtime is analysis-only: it classifies one persisted reply,
produces a typed sanitized artifact, and never sends mail or mutates CRM state.

The existing PostgreSQL LangGraph checkpoint store is the artifact store. No fourth reply
artifact table and no new dependency are introduced. Domain policy remains pure; application
ports and use cases own orchestration contracts; infrastructure owns the model, graph,
checkpoint, locking, and journal adapters; apps remain composition roots.

## Domain and application contracts

- `ReplyResultDTO` is a frozen Pydantic model with forbidden extra fields. It preserves the
  existing category, status, next-action, confidence, language, and evidence fields.
- `ReplyReviewReason` is a closed enum: `low_confidence`, `ambiguous`, `language_mismatch`,
  `missing_evidence`, `invalid_evidence`, and `unknown_category`.
- `unknown` is always `review_required`. The inclusive `0.80` threshold, nine categories,
  fixed next-action mapping, and unsubscribe precedence remain unchanged.
- Malformed evidence offsets (including booleans, coercible floats, negatives, empty or
  reversed ranges) fail safely as `invalid_response`. Valid but out-of-bounds ranges produce
  `invalid_evidence`, filter only invalid ranges, and preserve the original review reasons.
- `ClassifyReplyArgs` contains only `reply_id`. `ReplyClassifier` returns the existing typed
  `LLMResult[ReplyClassificationOutput]` through an application port.
- The classify use case loads the trusted organization and reply, validates the model result
  through domain policy, and returns the typed result with usage metadata.
- Reservation binds organization, run, request, reply, actor, thread, graph, prompt, model
  configuration, and an authoritative persisted `AgentRunRecord`. New threads are `str(run_id)`.
  Legacy `reply:{reply_id}` threads are accepted only when every persisted binding matches.

## Persistence, replay, and concurrency

Reply execution uses narrow ports for run reads, an execution fence, and idempotent terminal
journaling. A dedicated `ReplyRunJournal` may be added so existing agent-run fakes remain
compatible. Terminal events use deterministic UUID5 identifiers and append-once semantics;
the same payload replays and a different payload is rejected. Feedback remains append-only.

The graph is fixed as `reply-intelligence.v1` with `select`, `reserve`, `execute`, and
`complete` nodes. A per-organization/run PostgreSQL advisory lock is acquired before reading
or advancing a checkpoint. The lock and `AsyncPostgresSaver` use the same physical connection,
with non-blocking `pg_try_advisory_lock`; a busy caller returns `in_progress` without a model
call. The lock is held through the final checkpoint and journal reconciliation.

Checkpoint persistence uses `durability="sync"`. Lifecycle replay is fail-closed:

- absent or pre-reserve state resumes execution;
- reserved without a durable result returns `checkpoint_recovery_required` and never infers again;
- an executed validated artifact only completes;
- completed, failed, or refused states are read and reconciled without repeating inference;
- unknown identity or binding state is rejected before the model call.

Expected timeout, provider, schema, and size failures become sanitized durable failures. An
unexpected interruption leaves a reserved state and returns recovery required. Unknown usage
remains unknown; no synthetic zero cost is recorded.

## Prompt, tool, and bounds

The versioned prompt is `packages/core/revops/infrastructure/agent/prompts/classify_reply.v1.md`.
The original reply text, including Unicode and emoji, is preserved exactly. Deterministic
delimiters are verified absent rather than HTML-escaping text and changing evidence offsets.
The dedicated low-risk `classify_reply` tool has exactly one catalog entry and is not added to
global v1/v2 catalogs.

The reply gateway overrides only this runtime to a 1024-token output limit. The context budget
is a conservative 4096 UTF-8-byte estimate for prompt plus serialized schema, with framing and
output reserves; an oversized reply is refused rather than truncated. Model calls have a
20-second timeout and the full analysis deadline is 30 seconds. The sanitized envelope is
canonical compact JSON (`sort_keys`, `ensure_ascii=False`, `allow_nan=False`) and is at most
128 KiB before checkpointing and again at completion. Only whitelisted typed configuration,
usage, and metadata are persisted; raw reply text is never placed in run journal metadata.

## API, tests, and evaluation

The approved public contract for Item 5 is:

- `POST /replies` creates an organization-scoped reply; `GET /replies/{reply_id}` reads it.
- `POST /replies/{reply_id}/classify` reserves or replays one classification run.
- `GET /agent/runs/{run_id}/result` reuses the existing result route for the typed terminal artifact.
- `POST` and `GET /agent/runs/{run_id}/reply-feedback` append and list immutable corrections.
- Every mutating `POST` requires `Idempotency-Key` in the header, bounded to the existing 128-character
  convention. Organization identity comes only from authentication; it is never accepted from the body.
- Classification responses expose `run_id`, `status`, `replayed`, and an optional typed result. The
  status values are `in_progress`, `completed`, `failed`, and `recovery_required`; a replay returns the
  existing identity and artifact rather than creating a second run. Terminal reads use the direct
  authenticated artifact reader and do not construct a graph, initialize a provider, or perform RAG I/O.

Existing runtime behavior remains covered by regression tests.

Item 4 adds the mandatory offline runtime contract evaluation with a target of 1.00. Item 6
adds the 90 synthetic bilingual cases (five per category per language), independent baseline
metrics, and thresholds: accuracy >= 0.85, macro-F1 >= 0.80, unsubscribe recall = 1.00.
Integration tests must use real PostgreSQL checkpoints and prove concurrency, restart, and the
journal gap; in-memory fakes alone are insufficient. Unit, adversarial, security, and no-side
effect tests remain required.

## Rollout evidence

Run the focused Item 4 pilot before the unattended loop. Record graph/prompt versions, model
configuration, usage, latency, and failure codes. Only observed commands, file:line evidence,
and commits may close tasks. The supervisor queue remains the sole unattended work source.
