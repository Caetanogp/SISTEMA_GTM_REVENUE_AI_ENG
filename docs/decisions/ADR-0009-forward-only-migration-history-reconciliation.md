# ADR-0009: Forward-only migration-history reconciliation

- **Status:** accepted
- **Date:** 2026-09-13
- **Context spec:** SPEC-005

## Context

Alembic revision `b7c9d1e2f304` originally created generic deduplication candidate and alias tables.
It was later edited in place to declare typed tables and `ingestion_items.phone`. A database that
had already applied the original revision can consequently report the current head while retaining
the original schema. Existing integration tests exposed that state before executing application
behavior.

Resetting the database would discard evidence and repair only one environment. Editing the same
historical revision again would preserve the cause of the drift. Dropping the generic tables after
copying would violate the specification's additive and non-destructive migration constraints.

## Decision

Freeze the existing historical revisions and reconcile the two physical shapes through a new
forward Alembic revision. The revision conditionally creates the current typed schema, validates
legacy references and tenant ownership, and copies generic candidates, event relationships and
aliases while preserving identifiers and payloads. It fails atomically rather than guessing when
legacy data is unknown, orphaned, cross-tenant or conflicts with an existing typed row.

The generic tables, legacy event column and historical simple foreign keys remain present but are
excluded from Alembic autogeneration. Current adapters use only the typed schema. The repair's
downgrade performs no destructive reversal because the reconciled shape is the schema that the
existing historical source already declares.

## Consequences

- Correctly migrated databases receive an idempotent no-op apart from independently missing
  constraints or columns.
- Falsely stamped databases converge without data loss or physical reparenting.
- Rollout requires API and worker writers to be stopped until the migration and current application
  version are deployed; no temporary dual-write mechanism is introduced.
- Preserved legacy objects remain visible for audit and rollback safety but are not used for new
  writes.
- Future schema changes must use new revisions; applied migration files are immutable.
