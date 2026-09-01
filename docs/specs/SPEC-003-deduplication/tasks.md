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

- [ ] Add idempotent Celery scan publication/processing with bounds, retries, and duplicate-delivery tests.
- [ ] Add admin scan/status/candidate routes with pagination, replay, and queue-failure behavior.
- [ ] Add admin dismiss/merge/history/revert routes with stale and concurrency protection.

## Security and closeout

- [ ] Add adversarial coverage for authorization, tenant enumeration, malicious fields, bounds, and PII-safe events.
- [ ] Add integration coverage for matching, suppression, logical merge, canonical writes, and reversible aliases.
- [ ] Record the logical-merge and reversibility decision in an ADR and update README operations.
- [ ] Map every acceptance criterion to observed test/command evidence and update `.handoff/STATE.md`.
- [ ] Run `docs/playbooks/verify-before-done.md` in full and prepare the branch for review.
