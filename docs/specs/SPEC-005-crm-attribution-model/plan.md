# SPEC-005 implementation plan

## Approach

Implement the smallest PDF-aligned CRM attribution foundation from the inside out: pure domain
contracts first, application ports and validation second, then SQLAlchemy models/repositories and
an additive migration. Existing ingestion, deduplication and account-scoring paths are adapted only
where they create or read affected CRM records. No agent runtime or external integration is added.

## Layers and contracts

- **Domain:** `Campaign`, `Touchpoint`, and explicit opportunity-status validation. Keep framework
  free and make event timestamps/types and lifecycle values explicit.
- **Application:** tenant-scoped create/list ports and DTOs. Cross-entity organization checks happen
  before adapter writes. Reuse the existing unit-of-work boundaries rather than creating a second
  persistence transaction model.
- **Infrastructure:** SQLAlchemy `Campaign` and `Touchpoint` models, new fields and repositories,
  additive migration, indexes and canonical resolver integration for account/contact identifiers.
- **Apps:** only existing composition roots are adapted if required to expose internal persistence
  contracts. No public agent tool, UI route or external side effect is introduced.

## Chosen data contracts

- `Campaign`: `id`, `organization_id`, `name`, `source`, `channel`, `metadata`, `created_at`,
  `updated_at`.
- `Touchpoint`: `id`, `organization_id`, `account_id`, nullable `contact_id`, nullable `campaign_id`,
  `type`, `metadata`, `occurred_at`, `created_at`.
- `Interaction`: preserve account ownership; add nullable `contact_id` and `content`.
- `Opportunity`: preserve `stage` and `value`; add `status` constrained to `open`, `won`, `lost`.

Touchpoints may be account-level, contact-level or both; a campaign is optional because organic and
legacy events are valid. All foreign keys are tenant-checked in the application/repository boundary.

## Migration strategy

1. Add new tables and nullable columns/indexes without removing or rewriting existing data.
2. Backfill `opportunities.status = 'open'` for existing rows.
3. Validate status in the domain/application boundary and add a database check constraint only when
   the migration remains compatible with existing rows.
4. Verify `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head` against Docker
   PostgreSQL. Do not run destructive SQL or rewrite historical foreign keys.

## Trade-offs

- **Campaign fields instead of a separate attribution table:** matches the PDF's campaign
  `source/channel/metadata` contract without inventing an attribution algorithm before analytics.
- **Append-only touchpoints instead of inferred events:** preserves provenance and avoids unsafe
  retroactive claims.
- **Three opportunity statuses:** enough for the PDF's status requirement and stable for existing
  data; custom CRM stage names remain in `stage`.
- **Reuse existing unit of work:** avoids mixing transaction boundaries and follows SPEC-003's
  canonical-resolution constraints.

## Verification

- Domain and application unit tests cover status, timestamps, DTO strictness, tenant checks and
  canonical IDs.
- Persistence integration tests cover migration round-trip, CRUD relationships, indexes and
  cross-tenant rejection with real PostgreSQL.
- Existing ingestion/deduplication integration tests prove backward compatibility.
- Run Ruff, mypy, import-linter, unit, integration, adversarial and offline eval gates.
- Update `docs/requirements/PDF_TRACEABILITY.md`, `tasks.md` and `.handoff/STATE.md` with observed
  evidence only after the full verification gate.

## Rollout

This is a backward-compatible schema foundation. Merge only after Docker-backed migration and
integration tests pass. Do not launch the next queue item or expose these records to the agent until
the persistence contracts are verified.
