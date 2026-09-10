# ADR-0008: Logical Deduplication Merge and Revert

## Status

Accepted

## Context

Deduplication decisions must consolidate future reads and writes without destroying source data,
foreign-key history, or auditability. A physical merge would make a mistaken administrative decision
irreversible and would require rewriting unrelated records.

## Decision

Represent an approved merge as a typed, tenant-scoped alias from the selected source record to the
selected canonical master. Keep both source rows and their historical foreign keys unchanged. Record
the decision in an append-only, PII-safe event with an idempotency key. Revert deactivates the alias
and records a second append-only event; it does not redistribute data written while the alias was
active.

Merge and revert lock and revalidate the candidate, fingerprints, tenant, master selection, and
alias state before any side effect. An active alias cannot be reused as a master, and concurrent
requests are serialized by deterministic group locks and tenant-scoped event reservation.

## Consequences

- Normal reads and new account-bound writes resolve the alias to the canonical master.
- Historical records remain independently auditable and no destructive migration is required.
- Revert restores independent visibility of the original records without pretending later writes
  can be safely redistributed.
- Administrative approval remains a high-risk human decision; no agent tool can invoke these routes.
