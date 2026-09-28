# ADR-0011: Use explicit corpus identities for platform and organization knowledge

- **Status:** accepted
- **Date:** 2026-09-28
- **Context spec:** SPEC-007

## Context

SPEC-007 requires deployment-owned platform seed content and organization-private knowledge with
tenant override by `document_key`. The initial application contract addressed versions by a required
`organization_id`, which does not represent shared platform content without inventing a tenant or
introducing ambiguous null ownership.

## Options considered

1. **Sentinel organization** - simple foreign keys, but shared content appears to belong to a real
   tenant-shaped identity and can cross authorization boundaries.
2. **Nullable organization ownership** - avoids a sentinel, but every document, version, revision,
   and query must interpret `NULL` consistently and safely.
3. **Explicit corpus identity** - adds a small ownership entity, but makes platform ownership,
   tenant isolation, publication heads, and override resolution explicit and testable.

## Decision

Use `KnowledgeCorpus` identities. The platform corpus is a deployment-owned singleton. Each
organization has one uniquely owned organization corpus. Documents, immutable versions, chunks, and
corpus revisions reference `corpus_id`; only organization corpora carry an organization owner.
Tenant reads may resolve platform plus organization corpora, while tenant writes may target only the
organization corpus. Platform seed loading remains deployment-controlled.

## Consequences

- SQL constraints can enforce platform-singleton and organization-owner invariants.
- Application ports no longer need nullable or sentinel organization ownership for knowledge records.
- Item 3 must add the corpus table, foreign keys, uniqueness constraints, and migration tests before
  repository implementation proceeds.
- Override and corpus-head tests must prove that one organization cannot mutate or see another
  organization's private corpus.
