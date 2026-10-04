# Autonomous work queue

The only source of work for the SPEC-008 unattended loop. Items run in order and remain inside
their declared file scope. `scripts/autonomous_gate.py` is the sole judge of completion.

- **Tasks file:** `docs/specs/SPEC-008-context-retrieval/tasks.md`

## Item 1 - Retrieval contracts and domain pilot

- **Scope:** `docs/decisions/`, `packages/core/revops/domain/`, `tests/unit/domain/`
- **Requires:** agreed SPEC-008 spec, plan, and tasks with no unresolved architecture decision
- **Closes:** 2 tasks.md checkboxes
- **What:** record the retrieval ADR and implement pure query, score, provenance, budget, and
  embedding-space invariants.
- **Done when:** domain tests pass and the domain remains framework-free.

## Item 2 - Application retrieval contract

- **Scope:** `packages/core/revops/application/`, `tests/unit/application/`
- **Requires:** Item 1
- **Closes:** 3 tasks.md checkboxes
- **What:** define DTOs and ports, implement `RetrieveKnowledge`, and assemble bounded untrusted
  knowledge context with provenance and omission reporting.
- **Done when:** fake-port tests prove trusted tenant identity, provider behavior, compatibility
  failure, limits, budgeting, and data-only fencing.

## Item 3 - Persistence retrieval adapter

- **Scope:** `packages/core/revops/infrastructure/`, `tests/unit/infrastructure/`,
  `tests/integration/`
- **Requires:** Item 2
- **Closes:** 4 tasks.md checkboxes
- **What:** resolve active embedding spaces and implement the filtered pgvector query with active
  revisions, ready versions, tenant isolation, organization override, deterministic ordering, and
  provenance.
- **Done when:** PostgreSQL tests prove filtering occurs before ranking/top-k and existing indexes
  support the bounded query.

## Item 4 - Internal composition wiring

- **Scope:** `apps/`, `packages/core/revops/application/`, `tests/unit/apps/`, `tests/integration/`
- **Requires:** Item 3
- **Closes:** 1 tasks.md checkbox
- **What:** wire the retrieval use case through the internal composition root without exposing
  arbitrary corpus selection or changing write/HITL behavior.
- **Done when:** application wiring and tenant authorization tests pass.

## Item 5 - Adversarial retrieval coverage

- **Scope:** `tests/adversarial/`
- **Requires:** Item 4
- **Closes:** 1 tasks.md checkbox
- **What:** cover injection-shaped passages, secret-shaped passages, cross-tenant identifiers,
  historical revisions, invalid limits, and invalid budgets.
- **Done when:** adversarial retrieval tests pass and no passage can alter policy or trigger a tool.

## Item 6 - Retrieval eval and optional smoke

- **Scope:** `evals/`, `scripts/`, `docs/playbooks/`
- **Requires:** Item 5
- **Closes:** 2 tasks.md checkboxes
- **What:** add the deterministic `rag_retrieval_contract` eval and document an explicitly
  cost-confirmed optional live smoke.
- **Done when:** the offline retrieval contract scores 1.00 and live execution is never required
  by CI.

## Item 7 - Traceability update

- **Scope:** `docs/requirements/`, `docs/specs/`, `docs/decisions/`
- **Requires:** Item 6
- **Closes:** 1 tasks.md checkbox
- **What:** update PDF traceability and retrieval evidence with concrete file and line references.
- **Done when:** `python scripts/check_pdf_traceability.py` passes and every retrieval obligation
  has implemented or remaining-gap evidence.

## Item 8 - Closeout and verification

- **Scope:** `docs/`, `.handoff/`, `tests/`, `packages/`, `apps/`
- **Requires:** Items 1-7
- **Closes:** 1 tasks.md checkbox
- **What:** complete the security review, handoff evidence, full verification, and queue closeout.
- **Done when:** every task is checked, the full gate is green, and the handoff records command
  output and commit evidence.

## Loop rules

- Never edit this queue, the gate, supervisor controls, or `AGENTS.md` from an executor item.
- Return `architecture_required` for an uncovered component shape, state-machine edge, or other
  decision with multiple defensible implementations; return `HUMAN_REQUIRED` for product scope,
  security, dependency, destructive, external-action, or unverifiable decisions.
- No push, merge, work on `main`/`develop`, skipped tests, weakened checks, or checkout temp files.
- Commit one logical item before checking its task evidence.
