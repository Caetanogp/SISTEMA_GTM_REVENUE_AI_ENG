# SPEC-007: Versioned Knowledge Ingestion with pgvector

- **Status:** agreed
- **Owner:** Caetano
- **Roadmap phase:** 2
- **Created:** 2026-09-14

## Problem

The platform has no tenant-scoped, auditable knowledge corpus for ICP, product, pricing,
playbooks, brand voice, objection handling, outreach policy, or approved examples. Without
versioned ingestion, later retrieval and generation features cannot reliably identify which
content was approved, published, or retired.

## User stories

- As an organization admin, I want to submit and approve knowledge documents, so that my agents
  use controlled company context.
- As a platform operator, I want a trusted seed corpus, so that every tenant starts with approved
  shared knowledge without mutating the source corpus through the tenant API.
- As an auditor, I want immutable versions, chunk hashes, embedding metadata, and corpus revisions,
  so that publication and rollback are reproducible.

## In scope

- JSON API ingestion for UTF-8 text and Markdown documents in English or Portuguese.
- Eight controlled categories: ICP, product, authorized pricing, sales playbooks, brand voice,
  objection handling, outreach policies, and approved examples.
- Shared platform seed content and organization-private content with tenant override by
  `document_key`.
- Draft, explicit admin confirmation, asynchronous chunking and embedding, ready, failed,
  retired, and explicit historical activation lifecycle.
- PostgreSQL plus pgvector persistence, cosine HNSW index, immutable versions and append-only
  corpus revisions.
- Offline deterministic fake embeddings and an opt-in live OpenAI adapter using
  `text-embedding-3-small` with 1536 dimensions.
- Versioned JSON admin API under `/v1/knowledge` with tenant-scoped list/detail access,
  explicit confirmation and retirement, and historical revision activation. The exact public
  contract is recorded in ADR-0014.
- Admin authorization, idempotency, limits, audit events, security tests, and offline contract
  evaluation.

## Out of scope

- Retrieval, reranking, memory, prompt assembly, grounded generation, or RAG answer evaluation;
  these belong to SPEC-008.
- PDF parsing, arbitrary binary files, URL fetching, web crawling, translation, or automatic
  language detection.
- Automatic activation of a previous version, physical deletion, or tenant mutation of platform
  content.
- Production embedding credentials in tests or CI.

## Acceptance criteria

1. Unsupported category, language, format, empty content, oversized content (>1 MiB UTF-8), or
   excessive chunks (>500) is rejected before persistence.
2. Normalization uses Unicode NFC and deterministic newline handling; heading/paragraph-aware
   chunks are at most 3000 characters with at most 300 characters of overlap and stable hashes.
3. A document submission requires an `Idempotency-Key`; replay returns the original result and a
   conflicting payload with the same key is rejected.
4. A new version is draft until an authorized organization admin explicitly confirms it.
5. Confirmation dispatches asynchronous processing; publication occurs only after every chunk and
   embedding succeeds, atomically with its corpus revision.
6. Failed processing never activates a partial revision and preserves the previously active one.
7. Versions, chunks, publication history, and audit records are immutable; retirement is logical
   and historical activation is explicit and authorized.
8. A private ready version with the same `document_key` overrides the platform version only for
   its organization; platform content cannot be changed through the tenant API.
9. Embedding batches contain at most 64 inputs, use a 30-second timeout and at most two retries,
   and never fall back from a failed live call to fake embeddings.
10. The default offline path works without credentials; fake vectors are deterministic and
    normalized, and their non-semantic nature is documented.
11. Admin endpoints are tenant-scoped and expose metadata without returning full content in list
    responses; unauthorized, cross-tenant, injection-shaped, and secret-bearing inputs are tested.
12. The offline `rag_ingestion_contract` evaluation passes at 100%; live embedding smoke testing
    is optional, explicitly cost-confirmed, and excluded from CI.

### Admin API contract

The API exposes `POST /v1/knowledge/versions`, `GET /v1/knowledge/versions`,
`GET /v1/knowledge/versions/{version_id}`, `POST /v1/knowledge/versions/{version_id}/confirm`,
`POST /v1/knowledge/versions/{version_id}/retire`, and
`POST /v1/knowledge/revisions/{revision_id}/activate`. All routes require an administrator
Bearer token and derive tenant scope from its organization claim. Create and historical activation
require the `Idempotency-Key` header. List responses contain metadata only. The status-code and
replay contract is defined in ADR-0014.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| Knowledge document API | write | medium | explicit admin confirmation |
| Embedding provider | external | medium | no, bounded and auditable |
| Document retirement/activation | write | medium | explicit admin authorization |
| Platform seed loader | write | medium | deployment-controlled |

## Data model impact

Add `knowledge_corpora`, `knowledge_documents`, immutable `knowledge_document_versions`,
`knowledge_chunks` with `Vector(1536)`, and append-only corpus head/revision records. A corpus is
explicitly scoped as `platform` or `organization`; the platform corpus is a singleton and each
organization has its own corpus. Documents, versions, chunks, and revisions reference `corpus_id`.
Only organization corpora carry an organization owner; platform content never uses a sentinel
organization. Additive migration only; create the vector extension and HNSW cosine index when
absent, and never drop the extension on downgrade.

## Security considerations

Treat document text and metadata as untrusted data. Enforce tenant ownership, explicit allowlists,
schema validation, size limits, redaction-safe logs, no secret/content/vector logging, and append-
only audit history. No external content can alter policy or trigger a write.

## Eval impact

Add the offline `rag_ingestion_contract` suite covering validation, chunk determinism, lifecycle,
tenant override, idempotency, failure atomicity, and fake embedding determinism. Retrieval quality
and groundedness datasets are deferred to SPEC-008.

## Risks and open questions

- Live embedding availability and cost are operational concerns; offline fake vectors keep local
  development deterministic and do not claim semantic quality.
- Corpus revision writes must remain atomic across chunks, embeddings, heads, and audit events.
- The explicit corpus owner must remain the authorization boundary: tenant queries resolve an
  organization corpus and may read the platform corpus, while tenant writes can target only their
  organization corpus.
- The PDF remains the product source of truth; numbers and scope may change in a later approved
  spec revision.

## Approved architecture decision

Platform and organization knowledge use explicit `KnowledgeCorpus` identities. The platform corpus
is a deployment-owned singleton; organization corpora are uniquely owned by one organization.
`corpus_id` is the required foreign-key boundary for documents, immutable versions, chunks, and
corpus revisions. This avoids both a fake tenant sentinel and nullable ownership semantics.
