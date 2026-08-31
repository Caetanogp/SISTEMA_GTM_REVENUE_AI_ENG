# ADR-0005: Commit ingestion confirmation before Celery publication

- Status: accepted
- Date: 2026-08-30

## Context

SPEC-002 performs bulk writes only after an administrator previews and confirms a staged import.
The worker is asynchronous, while the API and database must remain available if Redis is briefly
unreachable. A transactional outbox would close the commit-to-publication crash window, but it is
explicitly deferred to SPEC-014.

## Decision

Confirmation commits the `queued` job state before publishing the Celery task. Publication uses
bounded broker retries. A publication error changes a still-queued job to `queue_failed`; a later
confirmation republishes it. Repeated confirmation of active or terminal jobs is idempotent.

The worker receives only tenant and job UUIDs, validates them, and delegates all business behavior
to `ProcessIngestionJob`. Database uniqueness, terminal item checks, and per-domain row locks make
duplicate delivery safe.

## Consequences

This keeps the confirmation transaction short and makes queue failure observable through polling.
There remains a bounded crash window after the database commit and before publication; idempotent
reconfirmation mitigates it. A future outbox in SPEC-014 will provide durable publication without
changing the application ports or public confirmation contract.
