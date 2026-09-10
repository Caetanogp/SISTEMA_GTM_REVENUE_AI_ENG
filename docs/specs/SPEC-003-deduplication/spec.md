# SPEC-003: Reversible account and contact deduplication

- **Status:** agreed
- **Owner:** Caetano Padoin
- **Roadmap phase:** 1
- **Created:** 2026-08-31

## Problem

The platform prevents exact normalized account domains and contact emails from being inserted
twice, but it cannot reconcile records that represent the same company or person under different
secondary identifiers. RevOps administrators need a safe way to find those records, select a
master, consolidate future behavior without losing provenance, and reverse a mistaken decision.

This is an administrative data-integrity capability. Matching is deterministic and explainable;
no candidate is merged automatically.

## User stories

- As an admin, I want to scan my organization's CRM for duplicate accounts and contacts, so that I
  can review data-quality problems across existing and imported records.
- As an admin, I want every candidate to include stable reasons and a score, so that I can explain
  why the records were paired.
- As an admin, I want to choose an existing record as the master, so that consolidation never
  silently invents field values.
- As an admin, I want to dismiss false positives and reverse a merge, so that data-quality actions
  remain controlled and recoverable.

## In scope

- Tenant-wide asynchronous scans for accounts, contacts, or both, bounded to 50,000 records and
  10,000 candidates per scan.
- Versioned `dedupe_v1` matching using exact normalized keys and stable reason codes.
- Account signals: normalized domain and normalized company name.
- Contact signals: normalized email, E.164 phone, and normalized full name within the same
  canonical account.
- An optional E.164 phone field on contacts and on the SPEC-002 JSON/CSV ingestion contract. Email
  remains required when a contact is supplied.
- Admin-only candidate review, dismissal, merge, merge-history, and revert endpoints.
- Logical master records backed by account/contact aliases; source records and foreign-key history
  are never deleted or physically reparented.
- Canonical resolution for normal reads and new writes, including ingestion, account scoring
  signals, and task creation.
- Idempotency, tenant isolation, PII-safe operational events, concurrent-decision protection, and
  bounded Celery retries.

## Out of scope

- LLM-assisted or fuzzy matching, auto-merge, or LangGraph tool exposure.
- Field-by-field master composition; the admin chooses one complete existing record.
- Frontend screens.
- Creating campaign, touchpoint, or new source-attribution entities. Existing ingestion provenance,
  enrichments, channels, interactions, opportunities, and tasks remain attached to their original
  records and are aggregated through canonical resolution where consumed.
- Creating a contact from phone alone; normalized email remains the primary identity.
- Physical FK rewrites, record deletion, or redistribution of post-merge data during revert.
- Merging two masters that both already have active aliases. One active master may absorb a
  standalone record; it may not be demoted in this version.
- Transactional outbox, dead-letter queues, and load hardening beyond the bounded worker contract;
  those remain in SPEC-014.

## Acceptance criteria

1. Given an authenticated admin and idempotency key, when it starts a tenant scan for accounts,
   contacts, or both, then the API persists and publishes one observable asynchronous scan; an
   identical replay returns the same scan and conflicting key reuse returns `409`.
2. Given CRM records within the configured bounds, when `dedupe_v1` completes, then each candidate
   contains an ordered pair, record type, score, stable reason codes, policy version, and record
   fingerprints, without crossing organization boundaries.
3. Given accounts with equal normalized domains or company-name keys, or contacts with equal
   normalized email, E.164 phone, or full-name key in one canonical account, when scanned, then the
   expected candidate is emitted with the documented score; fuzzy-only similarities are not.
4. Given a dismissed candidate, when a later scan sees unchanged fingerprints and policy version,
   then that pair is suppressed; changing either record or the policy makes it eligible again.
5. Given a pending candidate, when an admin approves it with one member as master, then a logical
   alias is created exactly once, both source records and historical FKs remain intact, and an
   append-only PII-safe merge event is recorded.
6. Given an account alias, when normal account reads, prioritization signals, or a new account-bound
   write use either member identifier, then they resolve to the master and aggregate existing
   interactions and opportunities across the alias set.
7. Given a contact or account already represented by an active alias, when ingestion encounters its
   strong identifier, then it returns the canonical master and does not attach new data to the
   alias.
8. Given an active merge, when an admin reverts it with an idempotency key, then the alias is
   deactivated exactly once, original records and original FKs become independently visible again,
   and post-merge data already written to the former master is not redistributed.
9. Given a stale fingerprint, an alias selected as master, a master demotion, two established alias
   groups, concurrent approval, or a cross-tenant identifier, when merge or revert is attempted,
   then it fails without a partial write or tenant disclosure.
10. Given an optional phone in JSON/CSV ingestion, when it is valid E.164, then it persists in
    normalized form; when invalid, the row receives a stable validation error and no raw phone is
    written to logs or deduplication events.
11. Given a non-admin or actor from another organization, when it starts, reads, dismisses, merges,
    or reverts deduplication data, then it receives `403` or tenant-safe `404` and no foreign data.
12. Given duplicate Celery delivery, broker failure, or worker retry, when a scan resumes, then
    candidate insertion and terminal scan state remain idempotent and observable.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| Administrative deduplication scan | internal read | low | no |
| Administrative candidate dismissal | internal write | medium | explicit admin action |
| Administrative logical merge/revert | internal high-risk write | high | required candidate review |

These endpoints are not exposed to the LangGraph allowlist. The pending candidate is the preview;
the authenticated merge or revert request is the human decision.

## Data model impact

- Add nullable `contacts.phone` with E.164 validation at the domain/application boundaries.
- Add tenant-scoped operational scan and typed candidate tables.
- Add typed account/contact alias rows with concrete foreign keys and reversible lifecycle fields.
- Add append-only deduplication events containing identifiers and reason codes, never raw PII.
- Use additive indexes and uniqueness for request idempotency, candidate pairs, and active aliases.
- Verify the migration with `upgrade -> downgrade -1 -> upgrade` against Docker PostgreSQL.

## Security considerations

- Phone, email, names, and candidate records are tenant data and are returned only to admins of the
  owning organization.
- Logs and append-only events contain IDs, hashes, status, scores, and reason codes but not raw PII.
- Every repository operation includes `organization_id`; foreign records produce the same `404` as
  missing records.
- Merge and revert lock and revalidate both records, candidate fingerprints, alias state, actor,
  and idempotency before a side effect.
- Scan limits and pair caps prevent same-key groups from causing unbounded memory or candidate
  explosion.

## Eval impact

No prompt, model, graph, or agent tool changes. Existing offline eval suites must remain green.
Deterministic matching quality is covered by unit, integration, concurrency, and adversarial tests.

## Risks and open questions

- Exact normalized secondary keys intentionally favor precision over recall. Broader fuzzy
  matching requires its own measured policy version and is deferred.
- Logical aliases require every current and future read/write path to use canonical resolution;
  architecture and integration tests enforce the paths touched in this repository.
- Broker publication retains the known commit-before-Celery crash window documented in ADR-0005;
  idempotent republication mitigates it until SPEC-014.
