---
agent: codex
updated_at: 2026-08-30
branch: develop
spec: SPEC-001-vertical-slice-account-prioritization
phase: "1 done - SPEC-001 persistence merged to develop. Item 5 (LangGraph) remains halted and needs plan mode with the user before any graph code."
status: persistence-merged-item5-halted
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

On `develop`, HEAD `2176685`, working tree clean. `feature/SPEC-001-persistence` is fast-forwarded
into `develop` at the same commit. The last verified gate for this slice was
`python scripts/autonomous_gate.py` => `GOAL ACHIEVED: all queue items done, full gate green`
(ruff, mypy, lint-imports, `pytest tests/unit tests/architecture -q`, check_agent_docs all OK).
Integration was also green: `pytest tests/integration -q` => 12/12 passed.

Item 5 is still halted by design. LangGraph node/checkpoint/interrupt wiring needs a user plan-mode
decision before any graph code is written.

## Done (this spec; full narrative in `.handoff/log/2026-08-30-0106-claude.md`)

- SPEC-001 persistence (tasks.md section 3) completed, verified, committed, and merged to
  `develop` at `2176685`. Models, first migration (10 tables), repositories +
  `SqlAlchemyUnitOfWork`, integration tests (12/12).
- Along the way, the repo retained the no-worktree rule after a real incident showed editable
  installs resolve `revops.*` through absolute paths baked in at `pip install -e` time.
- A gate-script indexing bug (`scripts/autonomous_gate.py` / `item_for_done_count`) was fixed when
  Item 4 exposed it.
- A schema defect was fixed: naive `datetime` columns were changed to `TIMESTAMPTZ` via
  `Base.type_annotation_map`.

## Next

1. Open Item 5 in plan mode with the user before writing any LangGraph code.
2. Resolve the open design questions for the graph: checkpoint state shape, `thread_id`
   identity, static vs. dynamic interrupt placement, and whether `DecideApproval` is called by the
   node or the API endpoint.
3. After the design is fixed, rewrite `.handoff/AUTONOMOUS_QUEUE.md` with concrete graph queue
   items, then only after that start any unattended loop.

## Gotchas

- `git checkout <branch>` can fail with `error: cannot stat '.claude': Invalid argument` when the
  target branch's `.claude/` tree differs from the current one.
- Never call `EnterWorktree` for this project. Editable installs resolve to absolute paths from
  installation time, so a worktree can silently run stale code.
- `docs/playbooks/autonomous-loop.md` is the shared source of truth for unattended-loop rules.
- `alembic downgrade` is in the unattended `ask` list and remains a human-run step.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline --decorate
```

## Open questions

- OneDrive/Defender exclusion for this folder would likely remove the checkout gotcha, but needs the
  user.
- Provider keys are still not configured (`.env` does not exist yet) for running the graph against a
  real model.
