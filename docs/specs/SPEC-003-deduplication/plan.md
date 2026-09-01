# SPEC-003 implementation plan

## Architecture

Domain owns E.164 phone validation, deterministic normalization, matching reasons/scores, scan and
candidate states, and alias invariants. Application owns DTOs, tenant-scoped ports, canonical
resolution, and scan/dismiss/merge/revert use cases. Infrastructure owns SQLAlchemy persistence,
the versioned matching adapter, and Celery publication/execution. API and worker remain composition
roots with no matching or merge decisions.

Use a dedicated `DeduplicationUnitOfWork`; do not expand either existing unit of work. Canonical
resolution is an application port implemented by the deduplication repositories. Each existing
composition root exposes a resolver backed by its own session and injects it into the use cases
that require canonical identity; no use case nests or mixes unit-of-work transactions. The resolver
returns a `CanonicalRecordGroup` containing the requested record's canonical master and all active
members, and its write variant locks that complete group deterministically until the caller commits.

## Matching policy

- Policy version is `dedupe_v1`.
- Text keys use Unicode NFKD, remove combining marks, casefold, replace non-alphanumeric runs with
  spaces, and collapse whitespace.
- Company keys additionally remove trailing legal suffix tokens from this versioned set: `inc`,
  `incorporated`, `llc`, `ltd`, `limited`, `corp`, `corporation`, `company`, `co`, `sa`, `ltda`,
  `eireli`.
- Account reasons/scores: exact normalized domain `account_domain_exact/100`; exact non-empty
  company key `account_name_exact/80`.
- Contact reasons/scores: exact normalized email `contact_email_exact/100`; exact non-null E.164
  phone `contact_phone_exact/90`; exact non-empty full-name key in the same canonical account
  `contact_name_account_exact/75`.
- Multiple reasons are retained and the candidate score is the highest reason score. UUIDs are
  ordered to make pair identity stable. SHA-256 fingerprints cover the normalized fields used by
  the policy and the canonical account ID for contacts.
- Scan canonical records only. Existing aliases are excluded as candidate members. A dismissed
  pair is suppressed only when record type, ordered IDs, both fingerprints, and policy version all
  match a previous dismissal.

## Alias model and transactions

- Aliases are logical: original account/contact rows and their FKs never move or delete.
- Tenant identity is explicit at the application boundary: `RecordAlias` carries
  `organization_id`, and scan creation receives the authenticated `requested_by` user separately
  from the tenant. Persistence adapters must never derive either value from the other.
- Separate account/contact alias tables provide concrete FKs. An active alias points directly to a
  non-alias canonical row; chains are forbidden.
- A standalone record may become an alias of another standalone record. A master with aliases may
  absorb a standalone record but must remain master. Two masters with aliases cannot be combined.
- Merge locks candidate, both records, and alias rows; verifies tenant, pending status, fingerprints,
  master selection, and idempotency; creates alias + append-only event and marks candidate merged in
  one transaction.
- Revert locks the active alias and merge event, records a new append-only event, and sets
  `reverted_at`/`reverted_by_event_id`. It never moves data created during the active merge.
- Dismissal records a stable reason code, actor, timestamp, and append-only event.

Normal account repositories resolve alias IDs to the canonical account. Organization listing hides
active aliases. Interaction and opportunity reads include every original account ID that currently
resolves to the requested master. Task creation and ingestion canonicalize account/contact IDs
before writes. Admin deduplication repositories retain raw access for review and revert.

## Persistence and asynchronous scan

- Add nullable `contacts.phone` and additive scan, account-candidate, contact-candidate,
  account-alias, contact-alias, and append-only event tables.
- Every row carries `organization_id`; all relevant indexes begin with it. Partial unique indexes
  enforce one active alias per source record. `(organization_id, idempotency_key)` protects scan
  creation and decision events.
- Candidate tables use concrete FKs and unique `(scan_id, left_id, right_id)`. Reasons are a bounded
  JSON array of stable codes; fingerprints are 64-character hashes.
- Scan status is `queued|queue_failed|processing|completed|failed`. Candidate status is
  `pending|dismissed|merged|stale`.
- `POST /scans` commits `queued` before publication. Broker failure conditionally marks
  `queue_failed`; an identical replay republishes. The worker task is
  `revops.deduplication.scan`, JSON-only, late-acknowledged, worker-loss rejected, and uses five
  bounded exponential retries.
- Worker locks the scan transition, reads at most 50,000 active records for requested types, builds
  exact-key buckets, and upserts at most 10,000 unique candidates. Candidates remain hidden until
  the scan reaches `completed`; exceeding a bound fails with a stable non-PII code.

## Public API

- `POST /admin/deduplication/scans` body `{record_types: ["account", "contact"]}` and
  `Idempotency-Key`; returns `202` new, `200` replay, `409` conflicting reuse, `503` publication
  failure with observable `queue_failed` state.
- `GET /admin/deduplication/scans/{scan_id}` returns status and derived counters.
- `GET /admin/deduplication/scans/{scan_id}/candidates` supports `record_type`, `status`, `offset`,
  and `limit<=100`; returns record summaries, score, reasons, and policy version.
- `POST /admin/deduplication/candidates/{candidate_id}/dismiss` body with enum reason
  `not_duplicate|insufficient_evidence`, plus `Idempotency-Key`.
- `POST /admin/deduplication/candidates/{candidate_id}/merge` body `{master_record_id}`, plus
  `Idempotency-Key`.
- `POST /admin/deduplication/merges/{merge_event_id}/revert` plus `Idempotency-Key`.
- `GET /admin/deduplication/merges` returns paginated merge/revert history.
- All routes require admin. Foreign IDs return `404`; stale/conflicting state returns `409`;
  malformed input returns `422`.

## Phone compatibility

`PhoneNumber` accepts only `+` followed by 8-15 digits and stores that exact normalized value.
JSON and CSV gain optional `phone`; existing clients remain valid. If any contact field is present,
email and full name remain required. Invalid phone is a stable row-level `invalid_phone` issue.
Phone is never emitted in logs, failure codes, audit events, or eval fixtures containing real data.

## Verification and rollout

- Unit: value object, normalization, suffixes, reasons/scores, fingerprints, state machines,
  suppression, canonical resolution, idempotency, stale/conflict paths.
- Integration: migration round-trip, typed FK repositories, API authorization/pagination, real
  Celery scan, canonical aggregation, ingestion/task canonicalization, merge/revert, concurrent
  decisions and duplicate delivery.
- Adversarial: cross-tenant enumeration, role bypass, malicious names/phones, candidate explosion,
  PII-safe errors and events.
- Run all verify-before-done commands and map every acceptance criterion to observed file:line test
  evidence before closure.

Roll out additively. No existing account/contact is automatically grouped. Administrators must run
a scan and approve each candidate.

## Autonomous loop preparation

After these three approved documents are committed, replace the SPEC-002 queue with scoped
SPEC-003 items. Pilot the domain-policy item, then allow a long loop only on this branch. The loop
cannot merge, push, touch `main`, weaken checks, or begin SPEC-004.
