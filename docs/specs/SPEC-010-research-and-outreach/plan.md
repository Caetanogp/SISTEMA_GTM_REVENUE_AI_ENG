# SPEC-010: Grounded Company Research and Follow-Up Preparation Plan

## Approach

Extend the existing single-agent runtime with two low-risk capabilities while keeping tenant
authorization, risk policy, HITL, and checkpoint ownership outside model output. Research is an
explicitly configured company-site adapter. Follow-up preparation consumes selected CRM context,
SPEC-008 retrieval, same-run research, and a versioned prompt. Natural generation is followed by a
second structured verifier that checks claim support, contradictions, commercial restrictions,
language, and references. A verifier rejection produces a bounded typed limitation; it does not
loop indefinitely.

The workflow remains one company per run and synchronous from the API's perspective. Existing
`create_task` remains the only business write and retains its approval checkpoint. No new database
tables or provider dependencies are introduced.

## Layer boundaries

### Domain

- Add immutable research source, fact, claim/reference, verification, limitation, and follow-up
  result value objects using stdlib only.
- Add stable statuses for `complete`, `partial`, `source_unavailable`, `evidence_insufficient`,
  `conflicting`, `refused`, and `failed`.
- Keep claim/reference validation deterministic and independent of HTTP, Pydantic, LLM, and SQL.

### Application

- Add strict Pydantic arguments and result DTOs for `research_company` and `prepare_followup`.
- Add ports for canonical account/contact resolution, bounded company research, context assembly,
  draft generation, claim verification, and artifact reading.
- Reuse existing account, contact, touchpoint, opportunity, and knowledge ports through a separate
  composition path; do not change ingestion or deduplication unit-of-work contracts.
- Add a use case that builds a bounded, fenced context and enforces evidence requirements before
  generation. Trusted tenant/run identity is supplied by `TrustedRunContext`.

### Infrastructure

- Implement a controlled HTTP adapter with explicit host/path authorization, HTTPS/443 only,
  no redirects/cookies/auth/proxy trust, DNS address validation and connect-IP/SNI pinning.
- Implement deterministic offline research and generation/verifier adapters for tests only.
- Adapt the existing LLM gateway so every new call retains `LLMUsage`; preserve legacy v1 resume
  behavior and use v2 only for new SPEC-010 runs.
- Extend the graph into checkpointed selection, reservation, execution, and completion steps.
  Completed artifacts are read from checkpoint state after restart and are never re-executed.
- Persist only bounded, sanitized artifacts in existing checkpoint/run-event boundaries.

### Apps

- Wire v2 dependencies in `apps/api/runtime.py` and preserve current start, stream, approve, edit,
  reject, and replay contracts.
- Add only `GET /agent/runs/{run_id}/result`; it is authenticated and organization-scoped.
- Do not add frontend, MCP, worker, send, calendar, or public external-source endpoints.

## Contracts

The two new tools are allowlisted with fixed `low` risk. Their schemas contain account/contact IDs,
objective, and explicit language; they cannot contain organization IDs, URLs, hosts, providers,
permissions, risk, or approval fields. Account/contact identity is resolved from trusted context and
validated before retrieval, network access, or model calls.

Research output includes account identity, status, facts, source URL, retrieval timestamp, content
hash, supporting excerpt, and limitations. Follow-up output includes subject, body, language,
rationale, claim references, source/retrieval provenance, and limitations. All persisted text is
bounded and sanitized; raw HTML is never returned.

## Runtime bounds

The hard limits are part of the contract: five tool calls; one business write; one research and one
follow-up result per run; three pages; 256 KiB response and 12,000 extracted characters per page;
two attempts per page for transient failures; 30-second research and 180-second run deadlines;
ten logical completions; 20 seconds per LLM call within the remaining deadline; 4,096 default and
16,384 hard context tokens; 500-character objective; 160-character subject; 6,000-character body;
128 KiB total new artifacts.

## Safe research adapter

1. Parse and normalize only configured `https` URLs on port 443.
2. Require exact authorized host and path prefix; the account domain alone is insufficient.
3. Resolve every attempt and reject loopback, private, link-local, reserved, and metadata addresses.
4. Connect to the validated literal address while retaining the original `Host` and TLS SNI; keep
   certificate verification enabled and revalidate on each attempt.
5. Reject redirects, unsupported media types, oversized bodies, and malformed responses.
6. Retry only transient timeout/rate-limit/server failures within the page and deadline budgets.
7. Extract bounded text, hash the raw response, and return source evidence without logging content.

## Context and grounding

Context is assembled in a deterministic order: request, account identity, relevant opportunities,
interactions/touchpoints, active ready knowledge with organization overrides, research facts, then
validated prior tool results. Each section is fenced as data and independently budgeted. Essential
product and commercial-policy evidence is required for a draft; missing evidence returns
`evidence_insufficient`. Website unavailability may produce a draft only when CRM and approved
knowledge support it, with an explicit limitation and no invented website facts.

Generation returns structured claims and references. Deterministic checks reject missing or foreign
references. The verifier receives only the bounded structured draft and evidence, and must return a
strict verdict. Any unsupported claim, contradiction, policy violation, invalid language, or malformed
verdict produces a bounded refusal/insufficient result without a second generation loop.

## Checkpoint and compatibility strategy

New runs use `single-agent-tool-runtime.v2` and store the selected tool, reservation, completed
research/draft artifact, counters, source/provenance, limitations, and per-call usage in JSON-safe
state. The graph writes after each lifecycle step. On restart, completed artifacts are returned from
state and the adapter is not called again. An interrupted external read is not automatically retried
after process restart. Existing v1 runs resume through the current composition and approval path.

The result endpoint reads a typed artifact through an application port. It does not invoke the graph,
network, RAG, or LLM. Run visibility is checked against the authenticated organization before the
artifact is read.

## Testing and evaluation

- Unit: domain values, strict schemas, canonical identity, source policy, bounded HTTP behavior,
  context budgeting, claim/reference validation, verifier outcomes, language and reuse.
- Integration: PostgreSQL checkpoint artifact persistence, restart read, active scoped retrieval,
  result API isolation, and legacy approval/replay compatibility.
- Adversarial: HTML/CRM/RAG prompt injection, delimiter escape, SSRF/DNS rebinding, redirects,
  fake citations, cross-tenant/run evidence, secret-shaped content, and write attempts.
- Offline evals: `research_outreach_contract` and `grounded_generation_contract`, deterministic,
  synthetic English/Portuguese, no network or credentials, exact score 1.00. Existing thresholds
  remain unchanged. Live smoke is optional and requires explicit cost/network confirmation.

## Trade-offs

- Authorized company pages are used instead of a paid search API to avoid a new dependency and
  uncontrolled provider data boundary.
- A verifier follows natural generation because the product needs personalized drafts, while
  deterministic references and bounded verification constrain unsupported claims.
- Checkpoint JSON is used instead of new tables because artifacts are run-scoped and bounded; a
  future durable artifact/reporting need requires a separate migration decision.
- A single agent remains the default; multi-agent delegation is evidence-gated by later roadmap
  specs.

## Rollout

Implement in the ordered tasks, run the focused pilot on a real queue item, then full verification.
Only after a new SPEC-010 queue has a clean baseline, a passing pilot, and gate evidence may a
bounded long supervisor be launched. No push or merge is part of this plan.
