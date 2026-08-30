# SPEC-002 implementation plan

## Architecture

Domain owns import/enrichment state transitions and value invariants using standard-library data
classes and enums. Application owns canonical records, result DTOs, use cases, and ports for
persistence, dispatch, and enrichment. Infrastructure owns CSV parsing, SQLAlchemy repositories,
the deterministic provider, and Celery. `apps/api` and `apps/worker` remain composition roots.

The canonical record is an account (`company_name`, normalized `domain`) plus optional contact
(`email`, `full_name`, `title`). CSV is converted to that record before application code runs.

## Public API

- `POST /ingestion/imports/json`: JSON body `{source, records}`.
- `POST /ingestion/imports/csv?source=...`: raw `text/csv` body, UTF-8 or UTF-8 BOM.
- Both require `Idempotency-Key` (1-128 characters); first creation returns 201, an identical replay
  returns 200, and a key reused with a different content hash returns 409.
- `POST /ingestion/imports/{job_id}/confirm`: returns 202 when dispatching work and 200 for an
  idempotent replay of a queued, active, or terminal job.
- `GET /ingestion/imports/{job_id}` returns job state and counters.
- `GET /ingestion/imports/{job_id}/items?offset=0&limit=100` returns tenant-scoped, paginated item
  outcomes. `limit` is at most 100.
- All routes are admin-only. Missing rights return 403; a foreign organization job returns 404.

File-level errors (empty input, invalid encoding, wrong content type/headers, more than 1,000 rows,
more than 5 MiB, unknown fields, or field-length violations) return 422 without staging. Row-level
errors are staged. An all-invalid parse becomes `validation_failed`; otherwise it waits for
confirmation.

## Persistence and processing

- `ingestion_jobs` stores tenant, actor, source, content hash, idempotency key, status, timestamps,
  and job-level failure details. It is unique on `(organization_id, idempotency_key)`.
- `ingestion_items` stores a normalized row, stable validation failures, account/contact outcomes,
  enrichment outcome, and references to created records. It is unique on `(job_id, row_number)`.
- `account_enrichments` stores immutable typed snapshots. It is unique on
  `(ingestion_job_id, account_id, provider, schema_version)` and has no update/delete repository
  method.
- Processing groups valid rows by normalized domain. Conflicting company names for the same domain
  and one email mapped to multiple domains are row-level validation failures. Existing accounts are
  never updated; new contacts can attach to one. Existing contacts are never relinked.
- The Celery task claims a nonterminal job, processes each account group in its own transaction,
  skips terminal items on repeat delivery, and derives terminal status from item outcomes.
- The `synthetic_v1` provider chooses fixed profile values from SHA-256 domain bytes and validates
  the result before persisting. Provider failure becomes an item error, not a rollback.
- The dispatcher commits job state before publishing. Publish failure records `queue_failed`; a
  confirmation retry may republish safely. The transactional outbox is deferred and documented in
  an ADR.

## Verification

- Unit tests: validators, CSV parser, status policy, grouping/conflicts, partial success,
  idempotency, fake enrichment, and no-write-before-confirmation behavior.
- Integration tests: additive migration round-trip, repositories, CSV and JSON API flows, actual
  Redis/Celery worker processing, duplicate delivery, queue failure recovery, pagination, and tenant
  isolation.
- Adversarial tests: malicious CSV/JSON text remains data, oversized fields are rejected, admin
  controls cannot be bypassed, and errors/logs do not leak cross-tenant or PII data.
- Run the complete `verify-before-done` gate plus the authorized migration round-trip.

## Autonomous loop preparation

Generalize `scripts/autonomous_gate.py` to read the active tasks file from queue metadata rather
than SPEC-001 constants. The new queue maps every task to explicit scope and closes count. Pilot a
single real queue item before the long run. The long run is limited to SPEC-002, may run the
authorized local migration round-trip, and cannot push, merge, or begin another spec.
