# ADR-0006: Canonical Identity Resolution Boundary

## Status

Accepted

## Context

Logical deduplication aliases preserve historical account and contact rows, but normal reads and
new writes must operate on the canonical master. The platform has separate transactional
boundaries for agent actions, ingestion, and deduplication. Sharing or nesting those transactions
would weaken atomicity and make composition-root ownership unclear.

## Decision

Define `CanonicalResolver` as an application port. Each unit of work exposes a resolver backed by
its own session. `resolve` returns the canonical master and all active alias members for reads;
`resolve_for_write` locks the complete group in deterministic UUID order until that unit of work
commits. Existing use cases receive the resolver explicitly and never open another unit of work.

Typed account and contact candidate/alias tables enforce tenant and record-type integrity at the
database boundary. Historical foreign keys remain unchanged; canonicalization changes only the ID
used by new account-bound writes and aggregate reads.

## Consequences

- Composition roots retain ownership of transaction scope.
- Ingestion, task creation, and account prioritization share one identity contract without mixing
  sessions.
- Concurrent decisions serialize on the same canonical group.
- The resolver must treat absent, wrong-type, and cross-tenant records as unavailable.
