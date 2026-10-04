# ADR-0012: Separate immutable corpus snapshots from activation history

- **Status:** accepted
- **Date:** 2026-09-28
- **Context spec:** SPEC-007

## Context

`knowledge_revisions` identifies an immutable active state, while historical activation is a
separate business event. Treating both as one row either violates manifest uniqueness on replay or
loses the actor and timestamp of repeated activation.

## Decision

Store each revision as a complete immutable snapshot with append-only
`knowledge_revision_entries`. Entries map one `document_key` to one version in the same corpus.
Compute `manifest_hash` from a versioned canonical JSON array sorted by document key. Store every
publication or historical activation in append-only `knowledge_revision_activations`, including
the action, actor, timestamp, selected revision, target version, and corpus-scoped idempotency key.

Activation reuses an identical existing snapshot and appends an event; a novel document-version
combination creates a new snapshot. The corpus head remains the only mutable pointer, and all
operations lock the corpus row within one unit of work.

## Rejected alternatives

- Mutating a revision to record activation breaks immutable audit history.
- Duplicating an identical revision makes manifest identity non-deterministic.
- Event-only history without entries cannot reproduce the active corpus state.
