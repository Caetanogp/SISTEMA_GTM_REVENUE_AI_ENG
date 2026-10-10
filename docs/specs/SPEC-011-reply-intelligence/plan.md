# SPEC-011: Reply Intelligence Implementation Plan

## Approach

Implement from the inside out: pure reply values and policy, application DTOs/ports/use cases, additive persistence, bounded prompt/tool/graph adapters, API composition, then datasets and full verification. Preserve existing SPEC-009 and SPEC-010 graph compositions and unit-of-work boundaries.

## Layers and contracts

- Domain: immutable reply identity, nine-category policy, confidence/evidence validation, language and unsubscribe precedence. Confidence below `0.80`, ambiguity, incompatible language, or invalid offsets produces `review_required` and `manual_review`. The fixed category-to-action mapping is recorded in `spec.md`. No framework or I/O imports.
- Application: reply DTOs, repositories and ports, artifact reader extensions, canonical resolver use, and reply-specific use cases.
- Infrastructure: SQLAlchemy models/repositories/migration, `classify_reply.v1` prompt, strict tool catalog entry, structured gateway adapter, and `reply-intelligence.v1` graph/checkpointer.
- API: authenticated reply registration, classification request, typed run result, and immutable feedback endpoints. Apps remain composition roots; no business logic in routers.
- Evals/tests: synthetic bilingual fixtures, contract scorer, deterministic baseline scorer, restart, concurrency, authorization, injection, and no-side-effect coverage.

## Persistence and transaction boundaries

Use three additive tables: `replies`, `reply_classification_requests`, and `reply_feedback`. Classification reservation, `AgentRun`, and the started event commit atomically before model execution. The reply-specific unit of work remains separate from ingestion and deduplication units of work. Idempotency keys are scoped by organization and operation; same payload replays, different payloads return conflict. Interrupted requests do not silently rerun a model call.

## Runtime design

The graph is a dedicated fixed-tool composition with selection, reservation, execution, and completion checkpoint nodes. It does not use an LLM router. Existing v1 resume and v2 research/outreach behavior remain unchanged. The model receives fenced reply data as untrusted content and must return a strict schema. One logical classification call is allowed, bounded by a 20-second model-call and 30-second analysis deadline, a 4,096-token context estimate, and a 128 KiB artifact limit before checkpointing.

## API and reader design

Registration uses `POST /replies` with `Idempotency-Key`; classification uses `POST /replies/{reply_id}/classify`; result reads reuse the authenticated agent-run result contract and direct artifact reader; feedback uses `POST` and `GET /agent/runs/{run_id}/reply-feedback`. Organization identity comes from authentication. Terminal GET must not construct a graph, initialize a provider, or perform RAG I/O.

## Rejected alternatives

- Mailbox integration: deferred to a later connector spec and would introduce credentials and external side effects.
- Automatic CRM updates or sending: violates the current low-risk analysis boundary and HITL rules.
- Thread-wide context: increases privacy, token, and ambiguity risk; current message is explicit scope.
- Reusing ingestion/deduplication units of work: mixes transaction invariants and makes replay behavior harder to prove.
- Multi-agent classification: contrary to the single-agent evidence gate and unnecessary for nine deterministic categories.
- Treating provider confidence as calibrated quality: unsupported without labeled provider evals.

## Test plan

Unit tests cover all categories in both languages, boundaries, precedence, DTO/schema validation, canonical identity, idempotency, authorization, feedback, tool policy, prompts, and artifact limits. Integration tests use PostgreSQL checkpoints and process restart. Adversarial tests cover injection, cross-tenant access, fake offsets, PII leakage, malformed outputs, and unintended writes. Regression tests retain existing v1/v2 runtime and result endpoint behavior.

## Eval plan

The 90 synthetic cases are five examples for each of nine categories in English and Portuguese. Contract scoring must be 1.00. The offline deterministic baseline must meet accuracy >=0.85, macro-F1 >=0.80, and unsubscribe recall 1.00, with metrics computed from independent predictions without reading expected labels. Existing eval thresholds remain unchanged; the new metrics are additive.

## Rollout and evidence

Run migration and focused pilot first, then the full verification playbook and PDF traceability checker. Record graph version, prompt version, usage, latency, and failure paths. Mark each task only after a command and file:line evidence is observed. The supervisor queue is limited to the eight task groups in `.handoff/AUTONOMOUS_QUEUE.md`.
