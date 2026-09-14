# SPEC-004: Requirements alignment and offline eval gate

- **Status:** in progress
- **Owner:** Caetano
- **Roadmap phase:** 0 - Foundation and design
- **Created:** 2026-09-12

## Problem

The project guide PDF is the product source of truth, but the repository does not yet expose a
complete, machine-checkable mapping from the guide to implemented evidence and planned work. Some
documentation also describes old roadmap positions as if they were current. The result is a risk of
implementing the next feature in the wrong order or treating an unimplemented capability as done.

## User stories

- As the product owner, I want every material PDF obligation mapped to repository evidence, so that
  missing capabilities and scope drift are visible before new implementation begins.
- As a maintainer, I want the mapping and offline eval command to run in CI without provider
  credentials, so that a green check means the repository's deterministic quality gate actually ran.
- As a coding agent, I want the roadmap and completed-spec references to reflect reality, so that
  handoffs do not restart obsolete work.

## In scope

- Record the source PDF SHA-256 and a complete page-spanning traceability matrix in
  `docs/requirements/PDF_TRACEABILITY.md`.
- Add a read-only standard-library checker for matrix shape, IDs, states, ownership, evidence and
  source-hash drift.
- Add unit tests for the checker and run it in CI.
- Make the eval workflow run the currently supported offline suites and threshold gate without
  requiring provider credentials. Live provider evals remain a separate future capability.
- Correct stale SPEC-001 references, README status/stack wording and the roadmap ordering to match
  the verified repository and the PDF.
- Reconcile the SPEC-001 Docker/pgvector checklist item only with observed command evidence.

## Out of scope

- RAG, pgvector retrieval, knowledge ingestion or context/memory implementation.
- LLM provider adapters, model routing, prompt changes or live evals.
- New CRM entities, tools, API endpoints, UI, workers, migrations or product behaviour.
- Changing existing product code merely to make a requirement appear implemented.
- Launching an autonomous development loop.

## Acceptance criteria

1. Given the checked-in source PDF, when the traceability checker runs, then its SHA-256 matches and
   the matrix has at least one valid row for every PDF page 1 through 20.
2. Given a matrix row, then it has a unique stable ID, source location, requirement, obligation,
   state, owner and evidence/gap fields with allowed values and no empty required field.
3. Given an `implemented` row, then its evidence is concrete repository file/line or command
   evidence rather than `N/A` or an unverified gap.
4. Given a `partial`, `planned` or `not-started` row, then ownership is assigned to a real or
   explicitly reserved roadmap spec and the gap is stated.
5. Given a changed source PDF, duplicate ID, malformed row or invalid state, then the checker exits
   non-zero with an actionable error and never modifies the matrix or repository.
6. Given a clean checkout without provider credentials, the eval workflow runs
   `python -m evals.run --suite all` followed by `python -m evals.gate`, and does not skip the gate.
7. The workflow exposes only suites implemented by `evals.run`, and its artifact path matches the
   reports produced by that command.
8. README, ROADMAP and SPEC-001 references no longer claim that merged work is pending or assign
   RAG/UI work to the wrong spec.
9. This change adds no production runtime behaviour, database migration or external side effect;
   the repository's existing unit tests and documentation checks remain green.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `check_pdf_traceability` | read-only quality control | low | no |

## Data model impact

None. The matrix is documentation and the checker reads files only. No database, migration,
tenant data or audit table is changed.

## Security considerations

The checker must not read `.env`, credentials or external services. It records only repository
paths, line references, command names and the public source PDF hash. No customer data or secrets
may enter the matrix, tests or CI logs.

## Eval impact

The offline `lead_scoring` and `tool_selection` suites remain the supported baseline. This spec
fixes their CI invocation and threshold enforcement; it does not add a model-backed scorer or
change the baseline data.

## Risks and open questions

- The PDF hash intentionally makes source changes visible; a future guide revision must update the
  matrix in the same reviewed change.
- The matrix is a coverage and honesty gate, not proof that a feature's runtime quality is good.
- Future specs must replace `planned` rows with concrete evidence as each capability is built.
- The next implementation spec requires owner decisions before `spec.md` is materialized; the
  roadmap is not a commitment to fixed numbers or scope.
