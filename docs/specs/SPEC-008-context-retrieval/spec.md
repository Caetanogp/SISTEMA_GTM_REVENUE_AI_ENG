# SPEC-008: Task-Scoped Knowledge Retrieval

- **Status:** draft
- **Owner:** Caetano
- **Roadmap phase:** 2
- **Created:** 2026-10-04

## Problem

SPEC-007 provides versioned, tenant-scoped knowledge documents, chunks, embeddings, and active
corpus revisions, but agent tasks cannot yet retrieve relevant chunks from that knowledge. Without
retrieval, task context cannot use approved product, ICP, pricing, playbook, brand, objection, and
policy knowledge with source and version provenance. Retrieval must preserve tenant boundaries and
the existing rule that retrieved content is untrusted data.

## User stories

- As an authenticated organization user, I want an agent task to retrieve relevant approved
  organization and shared platform knowledge, so that its analysis uses current, attributable
  context.
- As an auditor, I want every retrieved passage tied to its document, version, chunk, and active
  corpus revision, so that task evidence can be inspected and reproduced.
- As a platform operator, I want retrieval evaluation separated from answer-generation evaluation,
  so that retrieval regressions are visible without conflating them with model output quality.

## In scope

- A bounded application retrieval contract for a task-specific query using the existing embedding
  provider and knowledge repository boundaries.
- Semantic nearest-neighbor retrieval through the existing PostgreSQL/pgvector cosine index.
- Read access to the shared platform corpus and the authenticated organization's corpus, with the
  organization version overriding the platform version for the same `document_key`.
- Retrieval only from versions included in the active corpus revision and in `ready` state.
- Bounded result count, task-context token budget, deterministic tie handling, and explicit
  omission/truncation reporting.
- Provenance on each result: document key, version ID, chunk ID and ordinal, category, language,
  active revision ID, and retrieval score.
- Integration of retrieved passages into task-scoped context while keeping source passages
  clearly labeled as untrusted data.
- An offline `rag_retrieval_contract` dataset/eval for authorization filters, active-version
  selection, organization override, provenance, ranking, and budget behavior. It makes no claim
  about real-provider semantic quality.
- Optional, explicitly configured live retrieval smoke/evaluation if its provider cost is
  confirmed; it is never required by CI.

## Out of scope

- Hybrid lexical/vector search, reranking, and learned ranking. The roadmap identifies these as
  later retrieval improvements.
- Persistent business, user, or long-term memory stores. Existing thread checkpoint state remains
  separate and unchanged.
- Production answer generation, outreach generation, or changes to the agent's write tools and
  approval policy. Retrieval quality is measured independently; a generation-quality eval belongs
  to the generation capability that consumes this retrieval contract.
- Public arbitrary-corpus search endpoints or tenant selection of platform/organization scope.
- Document ingestion, editing, activation, retirement, parsing, web search, or external crawling.
- New embedding providers, credentials, or silent provider fallback.

## Acceptance criteria

1. Given an authenticated organization task, when retrieval runs, then the application derives
   organization identity from trusted task context and does not accept caller-supplied corpus or
   tenant scope.
2. Given platform and organization corpora, when the task retrieves knowledge, then it searches
   the shared platform corpus and only that task's organization corpus; a different organization's
   passages are never returned or used for ranking.
3. Given active revisions containing a platform and organization version with the same
   `document_key`, when candidates are assembled, then the organization version overrides the
   platform version and both are not returned as competing evidence for that key.
4. Given ready and non-ready or inactive versions, when retrieval runs, then only chunks belonging
   to versions present in the active corpus revision and marked `ready` are eligible.
5. Given a valid task query, when semantic search runs, then it uses the explicitly configured
   embedding provider and pgvector cosine similarity, enforces a result limit from 1 through 20,
   and resolves equal scores deterministically. Provider/model or vector-dimension incompatibility
   never causes scores from incompatible embedding spaces to be compared.
6. Given retrieved results, when they are returned to the application, then each result includes
   its source document key, version ID, chunk ID and ordinal, category, language, active revision
   ID, score, and passage text.
7. Given retrieved passages and a task-context token budget, when the context is assembled, then
   the budget is not exceeded, included passages retain their source attribution, and omitted
   results are reported explicitly.
8. Given retrieved text containing instruction-shaped or malicious content, when it is assembled
   into task context, then it remains fenced and labeled as untrusted data and cannot alter system
   policy, permissions, or trigger a tool action.
9. Given offline contract cases, when `rag_retrieval_contract` runs, then it deterministically
   verifies tenant filtering, active revision membership, overrides, provenance, ranking and budget
   behavior without network calls or credentials; its score is reported independently from any
   generation metric.
10. Given no live-provider configuration or explicit cost confirmation, when the offline suite and
    CI run, then no live embedding or retrieval request is made. Any optional live smoke requires
    explicit provider configuration and a cost-confirmation flag and emits no query, passage,
    vector, credential, or raw provider response.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| Task-scoped knowledge retrieval | read | low | no |
| Configured embedding provider for a task query | external read | medium | no; bounded and explicitly configured |

## Data model impact

Reuse SPEC-007's corpora, immutable versions, chunks, embeddings, active revision entries, and
existing pgvector cosine index. No persistent memory table is in scope. The implementation plan
must confirm whether these structures support efficient active-revision and tenant filtering
without a migration; any required schema change must be additive and preserve immutable history.

## Security considerations

Resolve tenant identity only from authenticated task context. Filter candidate rows by the
platform corpus and the caller's organization corpus before ranking or returning results. Treat
retrieved passages as untrusted external content, preserve source attribution, and prevent passage
text from changing policy or tool authorization. Keep retrieval bounded by query/result/token
limits. Never log query text, passage content, vectors, credentials, or raw provider responses.
Live embedding calls use only the task-specific query and the explicitly configured provider.

## Eval impact

Add `rag_retrieval_contract` as a deterministic offline suite with synthetic corpora and controlled
vectors. Report ranking/retrieval metrics and contract failures separately from generation quality.
Do not use deterministic fake embeddings as evidence of real semantic relevance. Live semantic
quality checks are optional, cost-confirmed, and excluded from CI.

## Risks and open questions

- Active-revision membership and organization override must be enforced before ranking, not applied
  only after top-k selection, or relevant eligible chunks could be hidden by ineligible ones.
- Platform and organization chunks may have different embedding model versions. The plan must
  define the compatibility behavior and migration/re-embedding implications without comparing
  incompatible vectors.
- The current task context builder uses a conservative character-based token estimate. The plan
  must decide whether this existing bound is sufficient for retrieval or whether retrieval needs a
  separately bounded allocation within the task's total context budget.
- The offline eval verifies retrieval contracts with controlled vectors; it does not establish
  production semantic quality. Define an optional live measurement approach without making it a CI
  dependency.

---
