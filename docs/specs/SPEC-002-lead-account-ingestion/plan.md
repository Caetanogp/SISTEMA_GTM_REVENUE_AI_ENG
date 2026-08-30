# SPEC-002 implementation plan

## Architecture

Domain owns import/enrichment state transitions and value invariants using standard-library data
classes and enums. Application owns canonical records, result DTOs, use cases, and ports for
persistence, dispatch, and enrichment. Infrastructure owns CSV parsing, SQLAlchemy repositories,
the deterministic provider, and Celery. `apps/api` and `apps/worker` remain composition roots.

The canonical record is an account (`company_name`, normalized `domain`) plus optional contact
(`email`, `full_name`, `title`). CSV is converted to that record before application code runs.

SPEC-002 uses a dedicated `IngestionUnitOfWork` and injected factory rather than extending
SPEC-001's `UnitOfWork`. Ingestion use cases own their transaction lifecycle through that port
because confirmation must commit before dispatch and processing requires multiple short
transactions. The UoW exposes tenant-scoped job, item, account-write, contact, and enrichment
repositories. Dispatch and enrichment remain separate ports.

The application use cases are `StageIngestion`, `ConfirmIngestion`, `ProcessIngestionJob`,
`GetIngestionJob`, and `ListIngestionItems`. The worker receives validated `organization_id` and
`job_id` values and delegates all business behavior to `ProcessIngestionJob`.

## Validation and idempotency

- Transport adapters reject unsafe batch-level structure before staging: wrong content type,
  invalid encoding or JSON envelope, bodies over 5 MiB, zero or more than 1,000 rows, non-object
  JSON records, incompatible scalar types, and unknown or duplicate fields/headers. CSV requires
  `company_name` and `domain`; `email`, `full_name`, and `title` are optional headers.
- Structurally safe rows are validated independently by the application. Missing, empty,
  oversized, or semantically invalid business fields become stable row-level error codes. If any
  contact field is present, `email` and `full_name` are required; `title` remains optional.
- Company, person, title, and source strings are trimmed. Domain and email use their domain value
  objects for normalization. Rows with conflicting normalized company names for one domain, or
  one normalized email mapped to multiple domains, are all marked invalid.
- The content hash is SHA-256 over canonical JSON containing trimmed `source` and ordered,
  structurally safe rows. Object keys are sorted, absent optional fields become `null`, and valid
  domain/email values are normalized. The transport format, JSON whitespace, CSV BOM, and line
  endings do not affect the hash.
- Staging uses one transaction to reserve `(organization_id, idempotency_key)`, compare the hash,
  and insert the job and all items. An identical reservation returns the existing job; a different
  hash raises an idempotency conflict. Staging never writes Account, Contact, or enrichment rows.

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

Batch-level structural errors return 422 without staging. Business-value errors, including field
length violations, are staged per row. An all-invalid parse becomes `validation_failed`; otherwise
it waits for confirmation. Creation returns 201 for a new preview, 200 for an identical replay,
and 409 when the same idempotency key is reused with a different hash. Confirmation returns 503
when publication fails and leaves the job observable as `queue_failed`; confirming that job again
retries dispatch.

## Transaction boundaries

### Confirmation

- `staged` and `queue_failed` jobs transition to `queued` in a short transaction that commits
  before Celery publication. A `queued` confirmation replay publishes again and returns 200,
  closing the known crash window between the database commit and broker publication.
- `processing` and terminal jobs return 200 without publication. Thus the logical queue transition
  occurs once while broker delivery is explicitly at-least-once.
- A publication error opens a new transaction and conditionally changes `queued` to
  `queue_failed`. It must not regress a job that an uncertain-but-successful publication already
  advanced to `processing` or a terminal state.

### Worker processing

- The first delivery transitions `queued` to `processing`; later deliveries may resume a job
  already in `processing`. `staged`, `validation_failed`, `queue_failed`, and terminal jobs are not
  processed.
- Each normalized domain is processed in its own transaction. The repository locks that group's
  item rows, then the use case rechecks terminal state after acquiring the lock. Account, contacts,
  enrichment, and item outcomes commit atomically for that group. A worker crash rolls the active
  group back, releases the locks, and a redelivery resumes remaining nonterminal groups.
- Account and contact inserts use database uniqueness without overwriting existing rows. Within a
  group, stable row-number order determines which row reports `created`; later occurrences report
  `duplicate`. An existing contact is never relinked.
- One enrichment snapshot is created per valid domain per job, including existing accounts. Its
  reference and outcome are applied to every valid item in the group. A provider failure is caught
  inside the group transaction so business rows remain committed with failed enrichment outcomes.
- Unexpected persistence errors roll back the group and escape to Celery for redelivery. A final
  transaction locks the job and completes it only when no nonterminal items remain. Validation,
  persistence, or enrichment failures produce `completed_with_errors`; duplicates do not.

## Persistence and processing

- `ingestion_jobs` stores tenant, actor, source, content hash, idempotency key, status, timestamps,
  and job-level failure details. It is unique on `(organization_id, idempotency_key)`.
- `ingestion_items` stores a normalized row, stable non-PII validation error codes, separate
  account/contact/enrichment outcomes, and references to created or found records. It is unique on
  `(job_id, row_number)`.
- `account_enrichments` stores immutable typed snapshots. It is unique on
  `(ingestion_job_id, account_id, provider, schema_version)` and has no update/delete repository
  method.
- `IngestionItemState` tracks account, contact, and enrichment outcomes separately. This is
  required for mixed outcomes such as an existing account plus a newly created contact. A missing
  contact is distinct from a skipped or failed contact operation.
- Processing groups valid rows by normalized domain. Existing accounts are never updated; new
  contacts can attach to one. Existing contacts are never relinked.
- The `synthetic_v1` provider chooses fixed profile values from SHA-256 domain bytes and validates
  the result before persisting. Provider failure becomes an item error, not a rollback.
- Job polling counters are derived from item rows rather than stored as a second mutable aggregate.
  The transactional outbox remains deferred and is documented in an ADR.

## Verification

- Unit tests: separate account/contact/enrichment outcomes, validators, CSV parser, status policy,
  grouping/conflicts, mixed outcomes, partial success, idempotency, confirmation republication,
  fake enrichment, and no-write-before-confirmation behavior.
- Integration tests: additive migration round-trip, repositories, CSV and JSON API flows, actual
  Redis/Celery worker processing, concurrent idempotency reservation, per-domain locking, rollback
  and restart during a group, duplicate delivery, queue failure recovery, pagination, and tenant
  isolation.
- Adversarial tests: malicious CSV/JSON text remains data, oversized fields are rejected, admin
  controls cannot be bypassed, and errors/logs do not leak cross-tenant or PII data.
- Run the complete `verify-before-done` gate plus the authorized migration round-trip.

## Autonomous loop preparation

Generalize `scripts/autonomous_gate.py` to read the active tasks file from queue metadata rather
than SPEC-001 constants. The new queue maps every task to explicit scope and closes count. Pilot a
single real queue item before the long run. The long run is limited to SPEC-002, may run the
authorized local migration round-trip, and cannot push, merge, or begin another spec.
