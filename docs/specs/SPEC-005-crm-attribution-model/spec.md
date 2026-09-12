# SPEC-005: CRM attribution model

- **Status:** agreed
- **Owner:** Caetano
- **Roadmap phase:** 1 - Code-first MVP foundation
- **Created:** 2026-09-12

## Problem

The project guide requires the CRM to represent campaigns, touchpoints, source attribution,
opportunities and interactions as first-class business state. The current schema supports accounts,
contacts, opportunities and account-level interactions, but cannot explain which campaign or
touchpoint produced an interaction or relate an interaction to a specific contact. This blocks
reliable attribution, later campaign analytics and grounded agent context.

## User stories

- As a RevOps operator, I want to record campaigns with their source, channel and metadata, so that
  acquisition provenance is preserved.
- As a sales user, I want touchpoints linked to accounts, contacts and campaigns, so that engagement
  history can be queried without reconstructing it from free text.
- As a RevOps operator, I want opportunities to have an explicit lifecycle status, so that pipeline
  and revenue queries can distinguish open, won and lost deals.
- As an agent use case, I want interactions linked to both accounts and optional contacts, so that
  future context retrieval can use the correct buying-group history.

## In scope

- Add a tenant-scoped `Campaign` persistence model with `source`, `channel`, JSON `metadata` and
  timestamps.
- Add a tenant-scoped `Touchpoint` persistence model linked to an account, optional contact,
  optional campaign, `type`, `occurred_at` and metadata.
- Add nullable `Interaction.contact_id` and `Interaction.content` while preserving its existing
  account relationship, channel, summary and timestamp.
- Add an explicit `Opportunity.status` with the compatibility values `open`, `won` and `lost`;
  existing opportunities default to `open` in the additive migration.
- Add domain entities/value objects, application ports/DTOs and SQLAlchemy repositories needed to
  create and query these records with organization scoping.
- Add additive Alembic migration, indexes and integration tests for relationships, tenant isolation,
  valid lifecycle values and backward-compatible existing rows.
- Keep canonical account/contact resolution from SPEC-003 on all new account-bound writes and reads.
- Update the traceability matrix and SPEC-005 evidence only after observed verification.

## Out of scope

- RAG, embeddings, knowledge ingestion, memory or context retrieval (SPEC-007/008).
- LLM gateways, prompts, agent routing, LangGraph tools, MCP or autonomous actions.
- External CRM connectors, campaign execution, email/calendar sending and enrichment providers.
- Attribution analytics, funnel dashboards, UI and public demo (later specs).
- Fuzzy identity resolution, automatic campaign inference or retroactive attribution of records that
  lack source data.
- Changing the existing deduplication alias semantics or physically rewriting historical foreign keys.

## Acceptance criteria

1. Given an authenticated organization, when a valid campaign is persisted, then its source, channel,
   metadata and timestamps round-trip with tenant ownership.
2. Given a valid account and optional contact/campaign in the same organization, when a touchpoint is
   persisted, then all supplied relationships, type, metadata and occurred time round-trip.
3. Given a touchpoint referencing another organization or a nonexistent record, when it is persisted,
   then validation rejects it without a cross-tenant relationship or partial write.
4. Given an existing interaction, when the migration runs, then its account, channel, summary and
   timestamp remain intact and its new contact/content fields are backward-compatible.
5. Given a valid contact in the interaction's account, when an interaction is persisted, then its
   optional contact relationship is queryable and tenant-scoped.
6. Given an opportunity created before this spec, when the migration completes, then its status is
   `open`; new opportunities accept only `open`, `won` or `lost`.
7. Given an invalid opportunity status, when the domain or application boundary validates it, then
   the operation fails before persistence.
8. Given campaign, touchpoint, interaction and opportunity queries, when the caller belongs to a
   different organization, then no records or relationship details are returned.
9. Given account or contact aliases from SPEC-003, when a new account-bound record is created or
   queried, then canonical resolution is used and historical records are not physically reparented.
10. Given duplicate delivery of an identical internal create request, when the request is retried,
    then the declared idempotency contract prevents an unintended duplicate or documents why the
    operation is intentionally append-only.
11. Given the repository's existing unit and integration suites, when the new migration and models
    are exercised, then no existing behavior or offline eval threshold regresses.
12. Given the source PDF traceability matrix, when this spec closes, then every new implemented row
    has concrete file/line or command evidence.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| CRM attribution persistence API | internal write | medium | authenticated authorization; no agent exposure |
| CRM attribution query ports | internal read | low | no |

These contracts are not added to the LangGraph allowlist and do not trigger external side effects.

## Data model impact

Additive migration only: `campaigns`, `touchpoints`, `campaign_id`/`content` fields as applicable,
nullable `interactions.contact_id`, and `opportunities.status`. Every new table is tenant-scoped
with foreign keys and indexes. Existing opportunity rows receive `open`; existing interaction rows
remain valid. No deletes, physical reparenting or destructive migration is allowed.

## Security considerations

All repositories must require `organization_id` internally. Relationship validation must prevent
cross-tenant foreign keys. Metadata and content are untrusted CRM data and are not instructions.
Tests must cover cross-tenant reads/writes and ensure no raw secrets or unrelated PII enter logs.

## Eval impact

No prompt or model change. Existing `lead_scoring` and `tool_selection` offline suites must remain
green. Add deterministic unit/integration coverage for lifecycle and relationship behavior; do not
claim attribution quality until campaign analytics and labeled data exist.

## Risks and open questions

- `open`, `won`, `lost` is the smallest compatible lifecycle; additional statuses require a later
  scope decision rather than silently expanding this migration.
- Touchpoints are append-only business events; source records without a campaign remain valid.
- Historical attribution is not inferred. Only explicit campaign/touchpoint data is attributed.
- The migration round-trip requires Docker PostgreSQL and must be verified before merge.
