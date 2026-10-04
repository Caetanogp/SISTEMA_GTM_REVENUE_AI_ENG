# SPEC-008: Task-Scoped Knowledge Retrieval Plan

## Approach

Implement one read-only application use case that turns trusted task identity plus a bounded query
into attributable knowledge context. The use case obtains one query embedding from the configured
`EmbeddingProvider`, resolves the platform and organization corpus identities internally, and asks a
retrieval repository for candidates that already satisfy active-revision, ready-state, tenant, and
organization-override rules. The repository applies the organization override before vector ranking
and `top-k` selection.

The first implementation is semantic vector retrieval only. It uses the existing PostgreSQL
pgvector cosine HNSW index and existing immutable corpus tables. Hybrid search, reranking, and
persistent memory remain later decisions.

## Layers and responsibilities

### Domain

- Add pure value objects for a bounded retrieval query, result limit, token budget, embedding space,
  retrieval score, source provenance, and a retrieved passage.
- Validate non-empty normalized queries, result limits from 1 through 20, positive token budgets,
  finite scores, supported embedding dimensions, and complete provenance.
- Keep the domain independent of Pydantic, SQLAlchemy, pgvector, embedding clients, and framework
  context types.

### Application

- Add strict DTOs for trusted retrieval context, query arguments, result provenance, omitted-result
  reporting, and the returned task knowledge context.
- Add `KnowledgeRetrievalRepository` as a `typing.Protocol`. Its main operation receives the
  authenticated organization ID, query vector, embedding model and dimension, and bounded limit;
  it returns candidates already filtered to the active platform/organization corpus view.
- Add a repository operation that resolves the active embedding space for the eligible platform and
  organization revisions. If ready active versions expose incompatible model or dimension values,
  the use case raises a typed compatibility error and returns no partial result.
- Add `RetrieveKnowledge`, which never accepts a caller-supplied corpus ID or scope, calls the
  configured embedding provider once for the query, invokes the repository, orders candidates with
  deterministic tie rules, and delegates budget fitting to the context assembler.
- Add `KnowledgeContextAssembler`, which emits clearly labeled untrusted-data sections with source
  provenance and reports candidates omitted by the token budget.

### Infrastructure

- Implement the retrieval port with SQLAlchemy against the existing knowledge tables.
- Resolve the active revision through `knowledge_corpus_heads` for the platform corpus and the
  authenticated organization's corpus.
- Join revision entries to document versions and chunks, filtering before vector ranking to active
  revision membership, `ready` status, requested embedding model, requested dimension, and the two
  permitted corpus identities.
- Select the organization source for a `document_key` whenever it exists, before applying vector
  ranking and the result limit. Keep all eligible chunks from the selected version; platform chunks
  remain eligible only when no organization version for that key exists.
- Order by cosine similarity descending, then `document_key`, version ID, chunk ordinal, and chunk
  ID ascending. Return a normalized similarity score rather than a database-specific distance.
- Use the existing HNSW vector index and revision/version indexes. Do not add a migration unless an
  `EXPLAIN`-backed test demonstrates that the existing indexes cannot support the bounded query; a
  schema change would require revising this plan before implementation.

### Apps and composition roots

- Wire the use case and repository in the existing application composition root without creating a
  public arbitrary-corpus search endpoint.
- Keep tenant identity in authenticated task context. The first integration point may expose an
  internal application contract for the agent runtime; public API behavior remains unchanged unless
  the acceptance tests require an existing route to carry the read-only context.
- Do not add generation, tool execution, HITL, or memory behavior to this spec.

## Contracts

The planned application port is conceptually:

```python
class KnowledgeRetrievalRepository(Protocol):
    async def resolve_active_embedding_space(
        self, *, organization_id: UUID
    ) -> EmbeddingSpace: ...

    async def search_active_chunks(
        self,
        *,
        organization_id: UUID,
        query_vector: Sequence[float],
        embedding_model: str,
        embedding_dimension: int,
        limit: int,
    ) -> Sequence[KnowledgeRetrievalCandidate]: ...
```

The exact DTO names may change during implementation, but the boundaries are fixed: authenticated
identity enters from the application boundary, corpus selection stays inside the use case/repository,
and SQLAlchemy details stay in infrastructure.

## Embedding compatibility

The query embedding model and dimension must match every ready version in the active platform and
organization corpus view. A mismatch returns a typed `embedding_space_incompatible` error. The
implementation never compares vectors from different model or dimension spaces and never silently
falls back to another provider or to fake vectors.

The current schema stores `embedding_model` and `embedding_dimension` on document versions and a
fixed 1536-dimensional pgvector column on chunks. The plan therefore expects no migration for the
first implementation. A migration is allowed only after an evidence-backed design revision.

## Context and security boundary

Retrieved passages are data. The assembler wraps each passage with a stable source label and
provenance fields, and the agent runtime must receive the collection as a data section distinct from
system and policy instructions. The assembler never evaluates passage text, extracts commands, or
changes authorization. Query text, passage text, vectors, credentials, and raw provider responses
are absent from logs.

The organization override is resolved before ranking so an ineligible platform passage cannot take a
top-k slot away from the organization replacement. Candidate filtering also happens before scoring
and result limiting. A caller cannot select the platform corpus, another organization, or a
historical revision.

## Test plan

### Unit tests

- Validate query normalization, limits, budgets, finite scores, embedding dimensions, provenance,
  deterministic ordering, and omission reporting.
- Test use-case authorization boundaries with fake repositories and embedding providers.
- Test platform-only retrieval, organization retrieval, organization override, inactive/non-ready
  exclusion, incompatible embedding spaces, provider failure, and empty results.
- Test untrusted-data fencing and that passage text cannot modify policy or tool authorization.

### Integration tests

- Seed platform and two organization corpora in PostgreSQL with active and historical revisions.
- Verify the query returns only the platform plus authenticated organization corpus and never leaks
  another organization's chunks.
- Verify organization override is applied before a small `top-k`, including a case where the
  platform score is higher.
- Verify ready-state and active-revision filters, provenance fields, score ordering, deterministic
  ties, and compatibility failure.
- Verify the existing schema/indexes support the bounded query and that no migration is needed.

### Adversarial tests

- Use prompt-injection-shaped and secret-shaped passages and assert they stay data-only and are not
  logged or executed.
- Attempt caller-supplied corpus IDs, organization IDs, historical revisions, oversized limits,
  and invalid budgets.

## Eval plan

Add `evals/datasets/rag_retrieval_contract.jsonl` and a deterministic scorer using controlled fake
vectors. Cases cover tenant filtering, active membership, organization override before top-k,
provenance, ordering, budget omission, incompatible spaces, and injection-shaped data. The suite
must score 1.00 offline and remain separate from generation-quality scoring. The live smoke is
optional, explicitly cost-confirmed, and excluded from CI.

## Rollout and verification

1. Add domain/application contracts and unit tests.
2. Implement the SQLAlchemy retrieval adapter and PostgreSQL integration tests.
3. Add context fencing, adversarial tests, and the offline retrieval eval.
4. Wire the internal composition root and optional live smoke documentation if needed.
5. Update PDF traceability and security evidence.
6. Run Ruff, mypy, import-linter, unit, integration, adversarial, eval, docs, secrets, and the
   autonomous gate with the isolated local database.

## Trade-offs

- Semantic-only retrieval is chosen to keep the first retrieval contract bounded and measurable;
  lexical hybrid search and reranking need their own quality evidence.
- A typed compatibility failure is chosen over silently dropping one corpus or comparing vectors
  from different spaces; partial context would be difficult to audit.
- Existing active revisions are reused instead of adding a mutable retrieval-specific index; this
  preserves immutable provenance and avoids a migration until query evidence requires one.
- Persistent memory is deferred so knowledge retrieval can be evaluated independently from thread,
  business, and user memory semantics.
