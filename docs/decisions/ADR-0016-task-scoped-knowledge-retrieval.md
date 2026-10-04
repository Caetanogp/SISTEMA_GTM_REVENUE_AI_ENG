# ADR-0016: Bound task-scoped knowledge retrieval to compatible active corpora

- **Status:** accepted
- **Date:** 2026-10-04
- **Context spec:** SPEC-008

## Context

SPEC-007 persists immutable, versioned knowledge in platform and organization corpora. Agent tasks
need attributable, bounded retrieval without weakening tenant isolation or treating retrieved text
as instructions. The existing pgvector schema stores 1536-dimensional vectors and already has the
active corpus revision model needed to reproduce the eligible source set.

## Decision

Retrieval is a read-only, task-scoped application capability. It derives the organization only
from trusted task context and internally selects the platform corpus plus that organization corpus;
callers cannot provide corpus, organization, or historical-revision identifiers.

Only `ready` document versions included in the active revision are eligible. When an organization
version has the same `document_key` as a platform version, the organization version replaces the
platform version before vector ranking and result limiting. Each result retains document key,
document version, chunk identity and ordinal, category, language, active revision, and score.

The initial query materializes this eligible set and ranks exact cosine distance with pgvector.
The existing HNSW index remains available for a later optimization, but approximate shared-index
filtering is not the correctness mechanism for this multi-tenant contract.

The result limit is inclusive from 1 through 20. Scores are ordered descending, with ties resolved
by document key, version ID, chunk ordinal, and chunk ID ascending. Task context fitting uses a
positive explicit token budget and reports excluded candidates rather than silently losing them.

Every ready active version must use the query embedding model and dimension. Any model or dimension
mismatch returns the typed `embedding_space_incompatible` failure; retrieval must not compare
vectors from different spaces or return a partial result. The initial implementation supports the
existing 1536-dimensional vector schema only and introduces no migration.

Query coordinates are validated as non-boolean, finite, and representable in float32 before the
database call. Zero vectors, null distances, non-finite distances, and corrupt eligible vectors
fail closed with sanitized typed errors. Provider and SQLAlchemy failures expose fixed error codes
without causes, SQL, bound values, vectors, or raw responses.

Retrieved passages remain untrusted data. The context assembler labels and fences them with their
provenance; it never evaluates their text, changes authorization, or alters policy/tool behavior.

## Consequences

- The domain exposes pure value objects for normalized queries, limits, budgets, embedding spaces,
  scores, provenance, passages, and deterministic ordering.
- The application and persistence layers can enforce compatibility and filtering before ranking
  without adding storage or a public arbitrary-corpus API.
- A future non-1536 embedding space requires an evidence-backed schema and plan revision rather
  than a silent fallback.

## Rejected alternatives

- Ranking all corpus rows and filtering tenant or override results afterward: this can consume a
  bounded result slot with an ineligible passage.
- Using a shared approximate HNSW scan as the initial correctness mechanism: filtering after an
  approximate scan can affect recall and makes tenant/override correctness harder to prove.
- Returning compatible subsets after a space mismatch: that produces incomplete, non-reproducible
  task context.
- Adding a retrieval-specific mutable index or migration now: the existing immutable revisions and
  vector index cover the approved initial contract without a demonstrated performance need.
