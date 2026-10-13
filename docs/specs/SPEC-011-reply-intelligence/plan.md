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

## Security closeout plan

### Ingestion invariant checks

Replace the four Bandit-reported `assert` statements in
`packages/core/revops/application/use_cases/ingestion.py` with explicit checks that raise a clear
internal invariant error if the supposedly validated record is inconsistent. Keep the existing
validation response for user input unchanged. Add regression coverage for normal staging and the
inconsistent contact record path so optimized Python cannot remove these guards.

### Reproducible Python dependency audit

Use `requirements-ci.txt` as an exact-version snapshot for the existing Python 3.12 Linux CI
environment. Resolve the declared runtime and dev dependencies with pip's cross-platform download
options for CPython 3.12/Linux x86_64, excluding the local project package. Do not use the
developer's global site-packages or OneDrive editable install. Update Python CI jobs to install the
lock input, install the local project with `--no-deps --no-build-isolation`, and run `pip check`.
The CI run validates actual Linux installation and execution. Run
`pip-audit --strict --no-deps -r requirements-ci.txt` against the same input. Review and update
vulnerable packages in bounded groups, checking compatibility with the project and rerunning the
full verification gate after each group.

The pip `requirements` format is selected over `pip lock`/`pylock.toml` because the official pip
documentation currently labels `pip lock` and pylock input support experimental. This uses the
existing pip workflow and introduces no lock-generation dependency. The lock is CI-platform
specific; developer setup remains available through the documented editable install.

Semgrep stays in its existing GitHub Actions security job with the current `p/default`, `p/python`,
and `p/secrets` rulesets. Its successful CI result is required for security closeout; no local
installation or ruleset change is proposed.

### Files and checks

- `packages/core/revops/application/use_cases/ingestion.py` and
  `tests/unit/application/use_cases/test_ingestion.py`: preserve invariant behavior; Bandit passes.
- `requirements-ci.txt`, `.github/workflows/ci.yml`, and `.github/workflows/evals.yml`: exact
  resolved dependencies are used consistently; `pip check` and pip-audit pass.
- `docs/security/SPEC-011-reply-intelligence-review.md`,
  `docs/specs/SPEC-011-reply-intelligence/tasks.md`, `.handoff/STATE.md`, and
  `.handoff/AUTONOMOUS_QUEUE.md`: record exact commands, evidence, and expanded Item 8 paths.
- Run Ruff, mypy, import contracts, unit, integration, adversarial, eval, traceability, docs,
  Gitleaks, Bandit, pip-audit, and the CI Semgrep job. Do not close Item 8 or restart the long loop
  until all required security checks pass.

### Bounded Item 8 closeout reconciliation

The approved verification repairs also changed existing platform-seed, worker, and integration-test
files to make the integration suite portable across Windows and Linux. Item 8 may update its queue
entry to include only these exact paths; this documents already reviewed repairs and does not
authorize a broader directory prefix or a change to gate, baseline, executor, or security policy:

- `apps/platform_seed.py`
- `apps/worker/main.py`
- `docs/playbooks/agent-tool.md`
- `docs/specs/SPEC-008-context-retrieval/plan.md`
- `docs/specs/SPEC-009-single-agent-tool-runtime/plan.md`
- `tests/integration/event_loop_policy.py`
- `tests/integration/test_attribution_behavior.py`
- `tests/integration/test_deduplication_api.py`
- `tests/integration/test_deduplication_persistence.py`
- `tests/integration/test_deduplication_worker.py`
- `tests/integration/test_ingestion_persistence.py`
- `tests/integration/test_ingestion_worker.py`
- `tests/integration/test_knowledge_retrieval.py`
- `tests/integration/test_knowledge_revision_persistence.py`
- `tests/integration/test_knowledge_worker.py`
- `tests/integration/test_persistence_repositories.py`
- `tests/integration/test_platform_seed.py`

The spec contains ten product acceptance criteria plus security closeout criterion 11. The
checkpoint-lock and canonical-artifact rows in the evidence table are implementation invariants
supporting existing criteria, not extra acceptance criteria.

## Rollout evidence

Run the focused Item 4 pilot before the unattended loop. Record graph/prompt versions, model
configuration, usage, latency, and failure codes. Only observed commands, file:line evidence,
and commits may close tasks. The supervisor queue remains the sole unattended work source.
