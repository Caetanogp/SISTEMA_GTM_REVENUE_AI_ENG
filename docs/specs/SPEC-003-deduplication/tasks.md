# SPEC-003 task checklist

## Specification and loop

- [x] Record the agreed `spec.md`, implementation `plan.md`, and ordered checklist.
- [x] Activate a scoped SPEC-003 autonomous queue and prove its pilot gate behavior.

## Domain and application

- [x] Add `PhoneNumber`, deterministic name keys, matching reasons/scores, fingerprints, and unit tests.
- [x] Add pure scan, candidate, alias, and decision state models with invariant tests.
- [x] Define deduplication DTOs, ports, canonical resolver, and a dedicated unit-of-work contract.
- [x] Implement and unit-test scan, list, dismiss, merge, revert, and canonical-resolution use cases.

## Persistence and compatibility

- [x] Correct the pre-merge generic candidate/alias schema to typed account/contact tables with
  concrete tenant-scoped foreign keys, active-alias uniqueness, and reversible event references.
- [x] Add tenant-scoped scan, typed candidate/alias, and append-only event models and repositories.
- [x] Add the nullable contact phone and deduplication tables in one additive Alembic migration.
- [x] Verify `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head`.
- [x] Extend JSON/CSV ingestion with optional E.164 phone and canonical account/contact writes.
- [x] Make account reads aggregate aliases and make new task writes resolve canonical accounts.

## Worker and API

- [x] Add idempotent Celery scan publication/processing with bounds, retries, and duplicate-delivery tests.
- [x] Add admin scan/status/candidate routes with pagination, replay, and queue-failure behavior.
- [x] Add admin dismiss/merge/history/revert routes with stale and concurrency protection.

## Security and closeout

- [x] Add adversarial coverage for authorization, tenant enumeration, malicious fields, bounds, and PII-safe events.
- [x] Add integration coverage for matching, suppression, logical merge, canonical writes, and reversible aliases.
- [x] Record the logical-merge and reversibility decision in an ADR and update README operations.
- [x] Map every acceptance criterion to observed test/command evidence and update `.handoff/STATE.md`.
- [x] Run `docs/playbooks/verify-before-done.md` in full and prepare the branch for review.

## Acceptance evidence

| Criterion | Observed evidence |
|---|---|
| 1 | `tests/unit/application/use_cases/test_deduplication.py:198`; `tests/integration/test_deduplication_worker.py:44` |
| 2 | `tests/unit/domain/policies/test_deduplication.py:57`; `tests/integration/test_deduplication_worker.py:44` |
| 3 | `tests/unit/domain/policies/test_deduplication.py:57`; `tests/unit/domain/policies/test_deduplication.py:68` |
| 4 | `tests/unit/application/use_cases/test_deduplication.py:225` |
| 5 | `tests/unit/application/use_cases/test_deduplication.py:262`; `tests/integration/test_deduplication_api_flow.py:32` |
| 6 | `tests/integration/test_deduplication_persistence.py:57` |
| 7 | `tests/integration/test_ingestion_api.py:19`; `tests/integration/test_deduplication_persistence.py:57` |
| 8 | `tests/unit/application/use_cases/test_deduplication.py:262`; `tests/integration/test_deduplication_api_flow.py:257` |
| 9 | `tests/integration/test_deduplication_api_flow.py:230`; `tests/integration/test_deduplication_persistence.py:141` |
| 10 | `tests/unit/infrastructure/test_ingestion.py:21`; `tests/integration/test_deduplication_worker.py:94` |
| 11 | `tests/integration/test_deduplication_api_flow.py:194`; `tests/integration/test_deduplication_persistence.py:57` |
| 12 | `tests/unit/infrastructure/queue/test_deduplication.py:13`; `tests/integration/test_deduplication_worker.py:44` |
| Verification | `pytest tests/unit -q` (`289 passed`); `pytest tests/integration -q` (`26 passed`); `pytest tests/adversarial -q` (`9 passed`); lint/import/docs/security commands passed. |
