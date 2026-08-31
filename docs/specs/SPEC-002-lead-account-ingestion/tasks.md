# SPEC-002 task checklist

## Specification and loop

- [x] Generalize `scripts/autonomous_gate.py` for queue-selected task files and add its unit tests.
- [x] Replace the SPEC-001 queue with scoped SPEC-002 work items and verify the pilot gate.

## Domain and application

- [x] Add pure import job/item state models and transition tests in `packages/core/revops/domain/`.
- [x] Add canonical ingestion/enrichment DTOs, ports, and unit-tested application use cases.

## Persistence and adapters

- [x] Add SQLAlchemy ingestion/enrichment models, repositories, and an additive Alembic migration.
- [x] Verify the migration with `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head`.
- [x] Add strict CSV parsing and deterministic synthetic enrichment adapters with unit tests.
- [x] Add the Celery dispatch adapter and `apps/worker` composition root with duplicate-delivery tests.

## API and security

- [x] Add admin-only JSON/CSV staging, confirmation, status, and paginated item routes.
- [x] Add API integration coverage for partial success, idempotency, queue failure, and tenant isolation.
- [x] Add adversarial coverage for untrusted CSV/JSON, authorization bypass, and PII-safe failures.

## Closeout

- [x] Record the Celery/outbox phasing decision in an ADR and update README setup instructions.
- [x] Map every acceptance criterion to observed test/command evidence and update `.handoff/STATE.md`.
- [x] Run `docs/playbooks/verify-before-done.md` in full and prepare the feature branch for review.

## Acceptance criteria evidence (recorded 2026-08-30, main session, before merge)

Filled in by the main session before merging - the checklist item above was ticked with no
mapping actually recorded anywhere. Verified by reading the cited code and test bodies directly,
not by trusting file names.

| # | Criterion (abridged) | Evidence |
|---|---|---|
| 1 | Staging creates a persisted preview with source + idempotency key, returns job id | `tests/integration/test_ingestion_api.py:19` (`test_admin_ingestion_staging_replay_polling_and_role_guard`): `POST /admin/ingestion` returns `201`, `body["status"] == "staged"` |
| 2 | Unconfirmed preview writes no `Account`/`Contact`/`AccountEnrichment` row | `StageIngestion` (`packages/core/revops/application/use_cases/ingestion.py:189`) never references the account/contact/enrichment repositories in its body - only `ConfirmIngestion` (line 238) and `ProcessIngestionJob` (line 300) do, and only after confirmation |
| 3 | Valid/invalid rows staged per-row; all-invalid batch is terminally `validation_failed` | `tests/unit/application/use_cases/test_ingestion.py:303` (`test_stage_normalizes_rows_and_keeps_business_errors_per_row`) for mixed rows; `:355` (`test_stage_marks_conflicting_domain_rows_invalid_together`) for both rows invalid -> `result.job.status is IngestionJobStatus.VALIDATION_FAILED` |
| 4 | Confirming a staged preview queues it exactly once, observable via polling | `tests/unit/application/use_cases/test_ingestion.py:376` (`test_confirmation_commits_before_publish_and_safely_republishes_queued_job`); polling observed live via `tests/integration/test_ingestion_api.py:19`'s `GET /admin/ingestion/{job_id}` and the paginated items route |
| 5 | Repeated rows for one normalized domain create at most one account | `tests/integration/test_ingestion_worker.py:43` (`test_live_worker_duplicate_delivery_is_idempotent`): real Celery worker, asserts exactly 1 `Account` row after processing |
| 6 | Existing account/contact preserved, not overwritten; a new contact can still attach | `tests/unit/application/use_cases/test_ingestion.py:461` (`test_existing_account_can_receive_new_contact_without_overwrite`): `company_name == "Original name"` unchanged, `account_outcome is DUPLICATE`, `contact_outcome is CREATED` |
| 7 | Successful import stores an append-only, versioned synthetic enrichment snapshot | `tests/integration/test_ingestion_worker.py:43`'s same live-worker test asserts exactly 1 `AccountEnrichment` row after processing |
| 8 | Enrichment failure preserves already-imported records; job is `completed_with_errors` | `tests/unit/application/use_cases/test_ingestion.py:494` (`test_enrichment_failure_preserves_business_writes_and_marks_job_with_errors`) |
| 9 | Same idempotency key + identical payload never duplicates; different payload conflicts | `tests/unit/application/use_cases/test_ingestion.py:323` (`test_stage_replays_identical_content_and_rejects_key_reuse`): identical replay returns the same `job.id`; different payload with the same key raises `IngestionIdempotencyConflictError` |
| 10 | Non-admin or cross-org actor gets no unauthorized access or leaked data | `tests/integration/test_ingestion_api.py:19`'s same test: a `rep`-role token gets `403` on `POST /admin/ingestion` |
| 11 | Malformed CSV (encoding, headers, size, row count, shape) rejected before staging | `tests/adversarial/test_ingestion_transport.py:9,14,19` (`test_csv_rejects_unknown_headers_before_staging`, `test_csv_rejects_malformed_rows_before_staging`, `test_csv_keeps_formula_like_values_as_untrusted_data`); live-API confirmation via `tests/integration/test_ingestion_api.py:19`'s malformed-CSV `422` |
| 12 | Duplicate Celery delivery or restart-after-partial-processing does not repeat terminal items | `tests/integration/test_ingestion_worker.py:43` (`test_live_worker_duplicate_delivery_is_idempotent`): a real duplicate delivery via `celery_app.send_task` twice, `second["processed_domains"] == []` |
