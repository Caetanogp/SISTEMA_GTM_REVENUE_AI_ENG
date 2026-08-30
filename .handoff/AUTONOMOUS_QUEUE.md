# Autonomous work queue

The only source of work for an unattended loop session (`docs/playbooks/autonomous-loop.md`).
The loop works this list top to bottom, one item at a time, and stops when it reaches the end of
the file or a genuine ambiguity that needs the user.

`scripts/autonomous_gate.py` is the sole judge of "done". The loop's own claim of completion is
never trusted.

Current baseline:
- SPEC-001 persistence is already merged on `develop`.
- Item 5 (LangGraph runtime integration and resume hardening) is complete in the feature branch.
- Item 6 (API composition root and run/approval endpoints) is complete in the feature branch.
- Item 7 (policy and security coverage) is complete in the feature branch.
- The remaining queue maps one-to-one to the eight unchecked boxes in SPEC-001 sections 7 and 8.
- The no-worktree rule still applies: unattended work runs in the main checkout, in a normal
  foreground session.
- `migrations/env.py` still excludes LangGraph checkpoint tables from autogenerate. Do not remove
  that filter.

---

## Item 8 - Synthetic demo seed

- **Scope:** `scripts/`, `packages/core/revops/infrastructure/persistence/`, `tests/`
- **What:** add a deterministic synthetic seed command for one demo organization with approximately
  30 accounts and related contacts, opportunities, and interactions.
- **Done when:** the seed command runs against the documented local database and the corresponding
  `tasks.md` checkbox is ticked.

---

## Item 9 - Tool-selection eval dataset

- **Scope:** `evals/datasets/`, `tests/`
- **What:** add approximately 10 synthetic tool-selection cases, including negative cases that must
  not select `create_task`.
- **Done when:** the dataset is valid JSONL, contains the required positive and negative cases, and
  the corresponding `tasks.md` checkbox is ticked.

---

## Item 10 - Lead-scoring eval dataset

- **Scope:** `evals/datasets/`, `tests/`
- **What:** add approximately 15 synthetic labelled account-scoring cases with stable expected
  outcomes.
- **Done when:** the dataset is valid JSONL, has the required labelled cases, and the corresponding
  `tasks.md` checkbox is ticked.

---

## Item 11 - Offline eval runner and baseline

- **Scope:** `evals/`, `tests/`, `docs/specs/SPEC-001-vertical-slice-account-prioritization/`
- **What:** implement the offline runner, deterministic gate, thresholds, and record the initial
  baseline report without requiring provider credentials.
- **Done when:** the runner and gate execute successfully on both datasets, the baseline is
  recorded, and the corresponding `tasks.md` checkbox is ticked.

---

## Item 12 - SPEC-001 decision record

- **Scope:** `docs/decisions/`, `docs/specs/SPEC-001-vertical-slice-account-prioritization/`
- **What:** verify that all decisions constraining future work are recorded in ADRs, adding or
  updating an ADR only where the existing records are insufficient.
- **Done when:** the decision record is complete and the corresponding `tasks.md` checkbox is
  ticked.

---

## Item 13 - Setup documentation

- **Scope:** `README.md`, `docs/specs/SPEC-001-vertical-slice-account-prioritization/`
- **What:** update user-facing setup and usage instructions so a stranger can run the vertical
  slice, including database migration, seed, API startup, authentication, and approval flow.
- **Done when:** the documented commands match the repository and the corresponding `tasks.md`
  checkbox is ticked.

---

## Item 14 - Acceptance evidence

- **Scope:** `docs/specs/SPEC-001-vertical-slice-account-prioritization/`, `.handoff/STATE.md`
- **What:** map all ten acceptance criteria to actual tests or commands and record concrete evidence
  for each one, including failure-path coverage.
- **Done when:** every criterion has a verifiable evidence reference and the corresponding
  `tasks.md` checkbox is ticked.

---

## Item 15 - Closeout handoff

- **Scope:** `docs/specs/SPEC-001-vertical-slice-account-prioritization/`, `.handoff/`,
  `.github/`
- **What:** perform the final closeout: update the checklist and handoff with observed evidence,
  fill the pull-request template for `develop`, and prepare the feature branch without touching
  `main`.
- **Done when:** the final gate is green, the handoff reflects the actual repository state, and the
  corresponding `tasks.md` checkbox is ticked. Opening or publishing the PR remains a user-owned
  action if no remote is configured.

---

## Rules for the loop

- Work items in order. Do not skip ahead even if a later item looks easier.
- Never touch a file outside the declared scope of the active item.
- Never use a worktree for this repo.
- Never merge or reconcile the branch yourself.
- Tick the matching box in `docs/specs/SPEC-001-vertical-slice-account-prioritization/tasks.md`
  as each item completes.
- Update `.handoff/STATE.md` after every item with evidence, not claims.
- If a new design decision has more than one defensible answer, stop and ask the user before
  coding.
