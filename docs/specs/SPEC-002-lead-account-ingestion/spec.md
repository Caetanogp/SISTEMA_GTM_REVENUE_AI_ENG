# SPEC-002: Lead and account ingestion

- **Status:** agreed
- **Owner:** Caetano Padoin
- **Roadmap phase:** 1
- **Created:** 2026-08-30

## Problem

Sales and RevOps operators need to load synthetic account and contact data into the platform before
they can prioritize accounts or demonstrate the agent workflow. The current repository only seeds
fixed demo data; it cannot accept an operator-supplied batch, validate it safely, preserve source
provenance, or enrich accounts asynchronously.

This is an inbound administrative capability. It is intentionally not an agent tool: an operator
must explicitly preview and confirm every bulk write.

## User stories

- As an admin, I want to submit account/contact records as CSV or JSON, so that I can load a
  synthetic RevOps dataset without editing the database.
- As an admin, I want to preview validation results before records are written, so that a malformed
  batch cannot silently change the CRM.
- As an admin, I want to confirm a valid batch and poll its progress, so that asynchronous work is
  explicit and auditable.
- As an admin, I want per-row outcomes and preserved import source, so that I can understand
  duplicates, validation failures, and what the import changed.

## In scope

- Admin-only inbound JSON and UTF-8 CSV import endpoints for up to 1,000 rows per batch.
- One CSV/JSON record represents one account and an optional contact; repeated normalized domains
  share one account.
- Persisted preview and explicit confirmation before any `Account` or `Contact` write.
- Required `source` metadata and idempotency key on every import creation request.
- Per-row partial success: valid rows persist, invalid rows are reported, and no existing record is
  overwritten.
- Minimal Celery/Redis worker path for asynchronous processing and polling endpoints for job and
  paginated item results.
- Deterministic, schema-validated synthetic account enrichment producing an immutable profile
  snapshot with industry, employee band, country, and summary.
- Tenant isolation, admin authorization, PII-safe logs, broker failure reporting, and idempotent
  worker delivery.

## Out of scope

- External CRM connectors, OAuth, pagination against a provider, or real enrichment credentials.
- A `Lead` entity; people are `Contact` records and companies are `Account` records.
- Upsert, reconciliation, merge, master-record selection, or source consolidation. Those belong to
  SPEC-003.
- LangGraph exposure, agent tools, LLM reasoning, HITL graph checkpoints, UI, SSE, webhooks, or
  export endpoints.
- Transactional outbox, dead-letter queues, rate-limit coordination, scheduled work, and load
  hardening. Those remain in SPEC-013/014.

## Acceptance criteria

1. Given an authenticated admin with a required idempotency key, when it submits at most 1,000
   valid JSON records or a valid UTF-8 CSV body, then the API creates a persisted preview with its
   source and returns its job identifier.
2. Given a staged preview, when it has not been confirmed, then no `Account`, `Contact`, or
   `AccountEnrichment` row has been written.
3. Given a batch with valid and invalid rows, when the preview is created, then valid rows are
   staged, invalid rows include a stable row-level error, and an all-invalid batch is terminally
   `validation_failed`.
4. Given a staged preview with valid rows, when its admin confirms it, then it is queued exactly
   once and can be observed through a polling endpoint.
5. Given repeated rows for one normalized domain, when the worker processes the batch, then it
   creates at most one account and attaches each non-duplicate contact to it.
6. Given an existing account domain or contact email, when the worker processes a row, then it
   preserves the existing record, reports the duplicate outcome, and does not overwrite or relink
   it; a new contact may still be added to an existing account.
7. Given a valid imported account, when asynchronous processing completes, then an append-only,
   deterministic synthetic enrichment snapshot is stored with provider and schema versions.
8. Given an enrichment failure for one account, when the import completes, then already imported
   records remain, that item records the failure, and the job is `completed_with_errors`.
9. Given the same idempotency key and identical request payload, when an admin repeats creation or
   confirmation, then no duplicate job, business record, or enrichment snapshot is created; a key
   reused with a different payload returns a conflict.
10. Given a non-admin or an actor from another organization, when it creates, confirms, or reads an
    import job, then it receives no unauthorized access or tenant data.
11. Given a CSV with invalid encoding, headers, size, row count, or field shape, when it is
    submitted, then the API rejects the file before staging unsafe input.
12. Given a duplicate Celery delivery or a worker restart after partial processing, when processing
    resumes, then terminal items are not repeated and outcomes remain consistent.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| Administrative import API | internal bulk write | high | explicit preview/confirm |
| Synthetic enrichment gateway | internal deterministic read | low | no |

The import API is not exposed to the LangGraph tool allowlist. Its explicit admin confirmation is
the human control for this user-initiated bulk write.

## Data model impact

- Add mutable operational tables `ingestion_jobs` and `ingestion_items`, both scoped by
  `organization_id`.
- Add append-only `account_enrichments` snapshots keyed by job, account, provider, and schema
  version.
- Preserve import provenance through the job source and item-to-created-record references; do not
  add a lossy single-source column to `accounts` or `contacts`.
- The migration is additive and verified with `upgrade -> downgrade -1 -> upgrade` against Docker
  Postgres.

## Security considerations

- CSV and JSON are untrusted data. Parsing is bounded, strict, and never executes spreadsheet
  formulas, instructions, or provider output.
- Raw uploads and PII are not logged. Staged normalized business fields are stored only in the
  tenant-scoped database.
- Import creation and confirmation require the `admin` role; repositories filter every read/write
  by `organization_id`.
- Idempotency keys, uniqueness constraints, item states, and immutable enrichment snapshots make
  retries and duplicate delivery safe.

## Eval impact

This spec adds no LLM prompt, model configuration, or agent tool. Existing offline eval datasets
and thresholds must remain green; deterministic ingestion behavior is covered by unit,
integration, and adversarial tests rather than a model-quality scorer.

## Risks and open questions

- Queue publication after the database commit has a known crash window. Confirmation retries and
  idempotent processing mitigate it; a transactional outbox is deliberately deferred to SPEC-014.
- The synthetic provider is a demo adapter, not a claim about real enrichment quality. A future
  provider replaces the adapter behind the same application port.
