# SPEC-007 implementation plan

## Approach

Implement ingestion as a Clean Architecture vertical slice. The domain owns category, language,
scope, lifecycle, normalization, chunking, and hash invariants. The application layer owns DTOs,
ports, authorization decisions, idempotency, and orchestration. Infrastructure owns SQLAlchemy,
pgvector, Celery, and HTTPX adapters. API and worker modules are composition roots only.

The lifecycle is `draft -> confirmed -> processing -> ready|failed -> retired`; historical ready
versions may be explicitly activated by an authorized admin. Processing builds all chunks and
embeddings before one transaction publishes a corpus revision. A failure leaves the current head
unchanged.

## Contracts and layers

- Domain: immutable value objects and pure functions for controlled categories, `en|pt`, `text|md`,
  tenant/platform scope, NFC/newline normalization, heading/paragraph chunking, stable hashes,
  size/chunk limits, and legal transitions.
- Application: `KnowledgeDocumentRepository`, `EmbeddingProvider`, `CorpusRevisionRepository`,
  `UnitOfWork`, `KnowledgeJobDispatcher`, and clock/idempotency ports using `typing.Protocol`.
- Infrastructure: SQLAlchemy models/repositories, pgvector type/index migration, deterministic
  fake provider, OpenAI HTTPX provider, Celery task, seed loader, and audit implementation.
- API: admin routes for create, confirm, inspect, list metadata, retire, and explicit activate;
  all routes require tenant-scoped authorization and `Idempotency-Key` where specified.

The public API is versioned under `/v1/knowledge`. `POST /versions` creates a draft and requires
`Idempotency-Key`; `GET /versions` lists metadata and `GET /versions/{version_id}` inspects one
version; `POST /versions/{version_id}/confirm` dispatches processing; `POST
/versions/{version_id}/retire` performs logical retirement; and `POST
/revisions/{revision_id}/activate` explicitly activates a historical revision and requires
`Idempotency-Key`. The API maps tenant-inaccessible resources to `404`, conflicts and invalid
lifecycle transitions to `409`, and does not accept a client-supplied organization scope. See
ADR-0014 for the complete response and error contract.

## Persistence and versioning

Use an explicit `KnowledgeCorpus` owner with `platform` and `organization` scope. Keep one
deployment-owned platform corpus and one uniquely owned corpus per organization; enforce the
scope/owner invariant in the database and application authorization. Use separate logical documents
and immutable versions. Store normalized content hash, source,
metadata, embedding model/dimension, processing status, idempotency key, and timestamps. Store
chunk ordinal, text/hash, structured metadata, and vector. Corpus heads point to active revisions;
revisions store an immutable manifest/hash. Migrations are additive. The platform-attribution
migration permits downgrade before seed data exists and blocks it atomically afterward, under
the user-approved compatibility exception in ADR-0015.

Each revision is a complete immutable corpus snapshot. Its membership is stored as one
`document_key -> version_id` entry per logical document, and its manifest hash is SHA-256 over a
canonical, versioned JSON array sorted by `document_key`. Activation is a separate append-only
event recording actor, timestamp, selected revision/version, action, and corpus-scoped idempotency
key. Reusing an existing snapshot is valid and does not duplicate the revision; it still appends a
new activation event. A novel combination of document versions creates a new snapshot. The corpus
head is the only mutable pointer. All publication and activation operations lock the corpus row
and commit through the shared unit of work.

Every document, version, chunk, and revision is addressed by `corpus_id`; tenant-scoped application
ports accept a resolved corpus identity rather than a nullable or sentinel organization. Tenant
reads may combine the platform corpus with the caller's organization corpus, with the organization
version overriding the platform version by `document_key`. Platform seed loading is deployment-
controlled and cannot be invoked through tenant admin routes.

## Chunking and embeddings

Normalize before hashing and chunking. Prefer headings and paragraphs, cap chunks at 3000
characters, and overlap by 300 characters without duplicating unstable boundaries. Embed in batches
of no more than 64, with a 30-second timeout and two retries. The live provider is explicit and
never silently falls back to fake vectors. The offline provider is deterministic, L2-normalized,
and clearly not a production semantic substitute.

## Worker delivery, retry, and audit

Celery carries only `corpus_id` and `version_id`, uses late acknowledgement and worker-loss
redelivery, and treats processing as at-least-once. The application derives the publication actor
from the immutable version. Confirmation replay republishes confirmed or processing work so a
broker failure after the confirmation commit is recoverable.

Provider calls retain their bounded two retries. The Celery task performs at most two additional
whole-job retries only for explicitly retryable provider failures and transient persistence
failures. Deterministic contract, state, payload, and programming failures are terminal. A replay
of a ready version succeeds without duplicating chunks, revisions, activation, or the corpus head.

Persist processing attempts in append-only `knowledge_processing_events` using deterministic event
identity per delivery, attempt, and event type. Store only identifiers, event type, retryability,
sanitized failure code, and timestamp. Never store document content, vectors, credentials, raw
provider responses, or exception messages. Commit the success event atomically with the ready
status, embedding model/dimension, chunks, revision, activation, and head; commit a terminal failure
event atomically with the failed status. See ADR-0013.

## Tests and evals

Add domain/application unit tests first, then migration/repository and API/worker integration tests.
Cover replay/conflict idempotency, tenant isolation and override, immutable history, failed
publication, authorization, prompt-injection-shaped content, secret-safe logging, limits, and
retry behavior. Add the mandatory offline `rag_ingestion_contract` eval with an exact 1.00 gate;
live embedding smoke is opt-in and never part of CI.

## Rollout

Materialize this spec, plan, tasks, and queue; reconcile handoff state; implement the domain and
chunker as the short pilot; run the gate and targeted tests; then implement remaining queue items
in order. Keep all supervisor temporary files outside the checkout. Run the full verification gate
before any merge into `develop`.

## Rejected alternatives

- Retrieval and RAG generation are deferred because ingestion and retrieval have distinct contracts
  and evaluation criteria.
- PDF/URL parsing is deferred to avoid hidden parser/network policy and unbounded ingestion scope.
- Automatic rollback is rejected because activation is a product decision requiring explicit audit.
- Live-to-fake fallback is rejected because it masks provider failure and produces misleading data.
- A sentinel organization is rejected because it pollutes tenant ownership and risks treating shared
  platform content as a real tenant. Nullable `organization_id` is rejected because `NULL` would
  encode ownership semantics inconsistently across documents, versions, revisions, and queries.
- Reusing `agent_actions` for worker audit is rejected because knowledge processing is not an agent
  run. Status plus logs alone is rejected because it cannot provide append-only attempt history.

## Platform seed decision

The platform seed is a deployment-controlled, one-shot composition root. Its manifest and UTF-8
content are immutable Python constants in
`packages/core/revops/infrastructure/knowledge_seed/`, not runtime files or URLs. This keeps the
trusted source inside the existing setuptools-discovered packages without changing `pyproject.toml`
or adding a package-data rule. The source is validated with the existing standard-library,
domain, and application contracts before any database or broker side effect. See ADR-0015.

The reviewed implementation must also:

- persist a positive seed revision on each platform version and reject a changed payload when the
  requested revision is not greater than the stored revision;
- enforce platform-versus-organization actor attribution in application adapters and integration
  tests, in addition to the XOR attribution checks;
- validate the complete normalized content with `chunk_content` for every manifest entry before
  opening the unit of work;
- serialize platform corpus creation and seed reservations with a database transaction lock so
  concurrent runs converge on the same idempotent result;
- compose database and broker settings without importing `apps.api` or `apps.worker`; and
- use the two-document approved manifest in ADR-0015 as the initial canonical source.

### Approved Item 9 execution contract (2026-10-03)

Implement `SeedPlatformKnowledge` in application, internal seed input/result DTOs, and narrow
repository ports for platform corpus creation/locking, latest seed revision lookup, and platform
draft reservation. Keep tenant reservation organization-only and keep the public Admin API schema
unchanged. Version DTOs retain an effective actor UUID and add optional `seed_revision`; adapters
read the effective actor from the appropriate user or system column.

Validate the complete manifest, strict positive integer revisions, normalized hashes, duplicate
keys, full document payload, and `chunk_content` limits before constructing a UoW. Stage the whole
manifest atomically, in document-key order. Idempotency keys are
`platform-seed:v1:<sha256(document_key UTF-8)>:<revision>` and remain within the existing 128-character
limit; revisions use the positive PostgreSQL Integer range. Compare content, category, language,
format, scope, and all metadata, not just the content hash.

Compare each requested revision with the maximum persisted revision, including failed and retired
versions. Lower revisions conflict. Equal revisions require identical payloads: confirm drafts,
redispatch confirmed/processing versions after commit, skip ready versions, and reject failed or
retired replays. Greater revisions create a new immutable version only after the previous version
is ready, failed, or retired. A greater revision while draft/confirmed/processing returns the safe
`seed_revision_in_progress` conflict; rerun after processing finishes. No manifest omission retires
or deletes a document. All entries are committed before any dispatch; partial broker failure leaves
confirmed versions recoverable by rerunning the same command.

Acquire a fixed-key PostgreSQL advisory transaction lock for seed loaders, then create/read and
lock the singleton platform corpus. Platform worker version locking must acquire the corpus row
before the version row; use the same corpus -> version order throughout platform processing and
publication. Do not change the organization corpus locking contract. Hold no database locks during
embedding or broker calls. Test seed/seed and seed/worker concurrency with independent sessions.

The additive persistence migration and exact attribution constraints are defined in ADR-0015.
Existing actor UUIDs and content are preserved. Backfill only new integrity projections; reject
inconsistent existing records. Upgrade -> downgrade -> upgrade must preserve real tenant records
before seeds; downgrade after any platform version or system attribution must fail before DDL and
leave both data and Alembic version unchanged. Run migration/concurrency tests in an owned isolated
schema using the existing supplied-connection and version-table-schema migration support; avoid
persisting platform seeds in the shared integration schema.

Compose `apps.platform_seed` with its own minimal environment settings and the existing session
factory, UoW, clock, Celery factory, and dispatcher. Match worker settings aliases/defaults, including
Redis broker database 1 and result backend database 2. Use the Windows-compatible selector runner.
The command accepts no runtime manifest, content path/URL, tenant, or actor override. Emit only safe
counts/identifiers and bounded static error codes; dispose resources on failure. Test raw injected
exceptions carrying a credential, URL, and document content against both stdout and stderr.

Tests must prove all validation/idempotency/lifecycle cases above, commit-before-dispatch, partial
dispatch recovery, database-level actor/corpus/organization enforcement, immutable history, fake
worker publication, same-key tenant isolation, tenant API rejection, and safe CLI output. Run the
full applicable verify-before-done commands, including gitleaks, and collect file:line evidence.

Prepare the ADR/plan/queue/state commit first. Apply the formal external baseline rollover with
the exact branch, previous/target SHA, sorted diff, and 11 completed task checkboxes. Archive the
original handoff at the Item 9 authorized log path only after rollover, then keep STATE.md concise.
Run one real executor turn with `-MaxTurns 1 -ChildTimeoutSeconds 1800`. Require an observed Item 9
gate before its checkbox, real implementation commits, and an independently verified gate selecting
Item 10 afterward. A stop solely at the intentional turn cap is expected, not proof of completion;
reconcile and commit that handoff before starting the `-MaxTurns 100` loop for Items 10-12.
