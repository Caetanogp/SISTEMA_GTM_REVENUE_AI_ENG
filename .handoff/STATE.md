---
agent: claude-code
updated_at: 2026-08-30
branch: feature/SPEC-001-persistence
spec: SPEC-001-vertical-slice-account-prioritization
phase: "1 in progress - SPEC-001 persistence (tasks.md section 3) fully done, gate green, not yet merged to develop. Item 5 (LangGraph) is next, needs a fresh session, Opus, plan mode."
status: persistence-complete-not-merged-item5-langgraph-next
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

On `feature/SPEC-001-persistence`, HEAD `d1557c9`, working tree clean. `docker compose ps` shows
`revops-postgres`/`revops-redis` healthy. **`python scripts/autonomous_gate.py` reports
`GOAL ACHIEVED: all queue items done, full gate green`** (ruff, mypy, lint-imports,
`pytest tests/unit tests/architecture -q`, check_agent_docs all OK). Integration suite also green:
`pytest tests/integration -q` — 12/12 passed.

**Not yet merged into `develop`.** Handoff happened before the merge step — do that first, see Next.

## Done (this spec; full narrative for section 3 in `.handoff/log/2026-08-30-0106-claude.md`)

- Domain + application layers (tasks.md sections 1-2), merged to `develop` at `adce03d`.
- **SPEC-001 persistence (tasks.md section 3) — all 5 items done, ticked, committed.** Models,
  first migration (10 tables), repositories + `SqlAlchemyUnitOfWork`, integration tests (12/12).
  Along the way: retracted `EnterWorktree` for this project entirely (a git worktree silently runs
  stale code — this repo's editable install resolves `revops.*` to absolute paths baked in at
  `pip install -e` time); found and fixed a real gate-script indexing bug
  (`scripts/autonomous_gate.py`'s `item_for_done_count`, see `QueueItem.closes`); found and fixed a
  real schema defect (every `datetime` column was naive `TIMESTAMP`, now `TIMESTAMPTZ` via
  `Base.type_annotation_map`) that Item 4's integration tests caught for real, exactly as designed.
  Full detail, every commit SHA, every command output: `.handoff/log/2026-08-30-0106-claude.md`.

## Next

1. **Merge `feature/SPEC-001-persistence` into `develop`** (self-service once verified — gate is
   already green above). This session did not do it: switching branches on this machine has a
   known, reproduced failure (`error: cannot stat '.claude': Invalid argument` — see Gotchas) and
   there wasn't time left to work around it safely. Try `git checkout develop && git pull &&
   git merge feature/SPEC-001-persistence` directly first; if it fails with that error, do not
   force anything — see the workaround in Gotchas.
2. **Item 5 (LangGraph node/checkpoint/interrupt wiring)** is next — marked `HALT:
   PLAN-MODE-REQUIRED` in `.handoff/AUTONOMOUS_QUEUE.md`. Per `AGENTS.md`'s standing
   complexity-flagging rule this needs a fresh session, in plan mode, with the user — not a
   continuation of unattended work. Open design questions it must resolve: checkpoint state shape,
   `thread_id` identity (`== agent_run_id`?), static vs. dynamic interrupt placement, who executes
   `DecideApproval` (the node or the API endpoint).
3. Once Item 5 is designed and scoped into queue items, `.handoff/AUTONOMOUS_QUEUE.md` needs
   rewriting for it (same pattern as the section-2-to-section-3 rewrite already done twice) before
   any unattended loop can run against it.

## Gotchas

- **`git checkout <branch>` can fail with `error: cannot stat '.claude': Invalid argument`** when
  the target branch's `.claude/` tree differs from the current one (OneDrive/Defender interference,
  suspected not confirmed). Workaround that touches no working-tree files: from a branch that is
  *not* the target, `git fetch . <source>:<target>` fast-forwards `<target>` without a checkout.
  Doesn't work if you're already on the branch you need to update (as was the case at handoff time)
  — the only path then is a plain `git checkout <target>` and hoping, or worst case share the diff.
- **Never call `EnterWorktree` for this project, in any mode.** `revops` resolves through a PEP 660
  editable install pinned to absolute paths from `pip install -e` time; a worktree silently runs
  stale code (a full queue item was drafted and "verified" this way, then found to have never
  actually run the new code — see `.handoff/AUTONOMOUS_QUEUE.md`'s "Rules for the loop"). Unattended
  work on this repo is always a plain foreground interactive session in the main checkout.
- **`.claude/settings.json`'s `ask` list is auto-denied, not auto-approved, under a `dontAsk`-style
  unattended session** — `alembic downgrade` is the concrete case so far (grouped with `git push`/
  `git merge` on purpose). Any queue item whose own done-criterion needs an `ask`-listed command
  needs a human to run that one command from a normal session; that's expected, not a bug.
- `docs/playbooks/autonomous-loop.md` is shared with Codex verbatim (`.codex/prompts/
  autonomous-loop.md` just points to it) — it already has every lesson above baked in. Adapt the
  *mechanics* (worktree tooling, permission-mode flags, cross-session messaging) to whatever Codex's
  own equivalents are; the *rules* (never worktree, foreground only, `ask`-list blocks unattended
  migrations, trust the gate script's exit code over any self-report) are tool-agnostic and apply
  as-is.
- All gotchas from `.handoff/log/2026-08-29-1929-claude.md` (psycopg's Windows event-loop policy
  requirement, the checkpoint-table autogenerate trap, pre-commit unreliability) still apply.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status                                  # confirm branch and clean tree first
git rev-parse --abbrev-ref HEAD             # currently feature/SPEC-001-persistence
docker compose ps                           # confirm revops-postgres, revops-redis healthy
python scripts/autonomous_gate.py           # should report GOAL ACHIEVED
pytest tests/integration -q                 # should report 12 passed
```

## Open questions

- `"Bash(alembic downgrade:*)"` in `.claude/settings.json`'s `ask` list vs. `allow` — open,
  deliberately not decided inside a loop (real security-policy tradeoff). Current pattern (human
  runs it once per migration) is fine for this project's pace.
- OneDrive/Defender exclusion for this folder (would likely fix the git-checkout gotcha above) —
  needs the user, not something fixable from inside a sandboxed session.
- Provider keys not configured (`.env` does not exist yet) — needed before Item 5's graph runs
  against a real model; the fake gateway covers everything until then.
