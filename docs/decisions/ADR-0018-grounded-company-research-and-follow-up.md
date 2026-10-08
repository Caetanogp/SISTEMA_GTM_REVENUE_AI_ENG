# ADR-0018: Grounded company research and follow-up preparation

- **Status:** accepted
- **Date:** 2026-10-07
- **Scope:** SPEC-010

## Context

The existing runtime can select bounded CRM tools and retrieve tenant-scoped knowledge, but it cannot
research an authorized company website or prepare a grounded bilingual follow-up. External pages,
CRM text, knowledge passages, and model output are untrusted. The feature must not introduce email
delivery, arbitrary web access, a second agent, or a new persistence schema.

## Decision

- Use only explicitly configured public pages on the account's company website for the first research
  source. Exact host/path authorization, HTTPS/443, DNS destination validation, no redirects, and
  bounded response limits are mandatory.
- Add `research_company` and `prepare_followup` as low-risk tools. They never send, schedule, mutate
  CRM records, or bypass the existing `create_task` HITL path.
- Produce English or Portuguese email drafts selected by the request. If the site is unavailable but
  CRM and approved knowledge are sufficient, continue with a visible limitation; never invent site
  facts.
- Generate a structured natural draft and run a second structured verifier over every claim. Invalid,
  unsupported, contradictory, or commercially restricted output becomes a bounded insufficient or
  refused result without endless regeneration.
- Store bounded run-scoped artifacts in existing checkpoint/event boundaries, add no tables, and
  expose them only through an organization-scoped typed result endpoint.
- New runs use v2 checkpoint lifecycle steps; existing v1 runs preserve their graph and approval
  semantics. Completed artifacts are reused after restart.

## Rejected alternatives

- **Paid search-provider API:** deferred because it adds cost, credentials, and a wider data boundary
  before the first controlled source is proven.
- **General crawler/browser:** rejected because it expands SSRF, JavaScript, retention, and runtime
  complexity beyond this bounded slice.
- **Extractive-only outreach:** rejected because the product needs personalized drafts; deterministic
  claim references and a second verifier constrain the added generation risk.
- **New artifact tables:** rejected because run-scoped bounded artifacts fit existing checkpoint
  storage and a durable reporting model belongs to a later spec.
- **Automatic human decisions:** rejected; HITL remains mandatory for the existing medium-risk write.

## Consequences

The first source is narrow and may return partial results, but its authorization and evidence are
reviewable. Live model quality is not proven by offline evals. A future provider, channel, bulk flow,
or durable artifact query requires a new scope decision.
