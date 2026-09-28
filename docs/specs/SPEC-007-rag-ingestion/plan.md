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

## Persistence and versioning

Use an explicit `KnowledgeCorpus` owner with `platform` and `organization` scope. Keep one
deployment-owned platform corpus and one uniquely owned corpus per organization; enforce the
scope/owner invariant in the database and application authorization. Use separate logical documents
and immutable versions. Store normalized content hash, source,
metadata, embedding model/dimension, processing status, idempotency key, and timestamps. Store
chunk ordinal, text/hash, structured metadata, and vector. Corpus heads point to active revisions;
revisions store an immutable manifest/hash. Migrations are additive and downgrade-safe.

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
