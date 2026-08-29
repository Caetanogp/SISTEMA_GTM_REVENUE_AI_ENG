---
agent: claude-code
updated_at: 2026-08-29
branch: feature/SPEC-001-persistence
spec: SPEC-001-vertical-slice-account-prioritization
phase: "1 blocked - autonomous loop for tasks.md section 3 (persistence) halted itself before Item 1's gate could ever go green, due to an environment blocker outside the loop's declared file scope"
status: persistence-item1-blocked-on-editable-install-env-issue
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

Launched the autonomous loop per `docs/playbooks/autonomous-loop.md` against
`.handoff/AUTONOMOUS_QUEUE.md` items 1-4. `EnterWorktree` created
`.claude/worktrees/spec-001-persistence-loop`; renamed to `feature/spec-001-persistence-loop`
(`git branch -m`). Confirmed clean tree, correct branch, `docker compose ps` showed
`revops-postgres` healthy. Wrote a full draft of Item 1 (models + tests), then hit a real
environment blocker before the gate could ever pass — **stopped per the standing rule in the
seed prompt and `AUTONOMOUS_QUEUE.md`: "if you hit ... a scope violation you can't resolve within
an item's declared file scope ... stop, write the full situation to STATE.md ... and end your
work."**

**The blocker, with evidence:**

`revops` is resolved via a **global, per-user** Python install
(`C:\Users\Caetanogp123\AppData\Roaming\Python\Python312\site-packages`, *not* a project-local
`.venv`), through a PEP 660 editable-install finder
(`__editable__.agentic_revops_platform-0.1.0.finder.__path_hook__`) that maps `revops.*` submodules
to **absolute file paths baked in at `pip install -e ".[dev]"` time** — the main checkout's
`packages/core/revops/...`, per `tasks.md`'s "verified 2026-08-26" note and every prior handoff
log's install command. A git worktree is a genuinely separate directory tree on disk; the finder
has no knowledge of it and keeps resolving to the main checkout's files regardless of `cwd`.

Proved this directly, twice:
1. Added a diagnostic assertion inside a worktree test file: `models.__file__` printed the **main
   checkout's** `packages/core/revops/infrastructure/persistence/models.py` path — the untouched
   stub (`Base` only, no tables) — even though the worktree's copy of that same file had already
   been rewritten with all ten tables. `sys.path` confirmed the AppData global site-packages +
   the `__editable__...finder.__path_hook__` entry above, no project `.venv` anywhere in it.
2. Ran `python scripts/autonomous_gate.py` for real (not simulated) from inside the worktree: it
   executed `pytest tests/unit tests/architecture -q` and failed with the **exact same** symptom —
   `Base.metadata.tables` empty, `KeyError: 'agent_actions'` etc. — proving this is not just my own
   diagnostic script's artifact, it is what the gate itself would see for every item, forever.
   (`lint-imports` also failed in that same run, but for an unrelated, pre-existing cause: a
   Windows `cp1252` console `UnicodeEncodeError` inside import-linter's own `rich`-based renderer
   when it prints its report — worth a look someday, not part of this blocker and not something I
   touched.)

**Why I did not fix this myself, both live options considered and rejected:**

- **Reinstall editable (`pip install -e ".[dev]"`, or `uv sync` — `uv` is not even on `PATH` here,
  confirmed) from inside the worktree.** This is not in Item 1's declared scope, but more importantly
  it would rebind a **global, shared, per-user** Python environment's package resolution away from
  the main checkout and onto a worktree directory that gets deleted when this job/session ends —
  breaking `import revops` for the user's own main-checkout terminal and any other concurrent
  session on this machine the moment the worktree is removed. A hard-to-reverse, shared-system
  side effect the "Executing actions with care" rules require confirming first, not guessing on.
- **Add a `conftest.py` that fixes `sys.path` before any test imports `revops`.** Investigated: it
  would need to be a *root*-level `conftest.py` (a nested one under `tests/unit/infrastructure/`
  loads too late — `revops` is already resolved to the stale path by the time domain/application
  tests import it earlier in the same pytest session, alphabetically before `infrastructure`). A
  root `conftest.py` is outside every queue item's declared scope, and `scripts/autonomous_gate.py`'s
  own `scope_violation()` check would correctly flag it and halt anyway.

Neither is a decision the loop should make unilaterally. This needs the user to pick a fix (see
`## Next`).

**State of Item 1's draft work** (commit `<see git log on this branch — committed as WIP, unverified>`):
`packages/core/revops/infrastructure/persistence/models.py` (all ten tables — `organizations`,
`users`, `accounts`, `contacts`, `opportunities`, `interactions`, `tasks`, `agent_runs`,
`agent_actions`, `approvals` — following the domain entities field-for-field, `agent_actions.run_id`
nullable per ADR-0002, no `onupdate`/cascade-delete on the three audit tables, `organization_id`
indexed everywhere, unique `(organization_id, domain)` on accounts and `(organization_id, email)`
on contacts) plus `tests/unit/infrastructure/{__init__.py,persistence/__init__.py,persistence/test_models.py}`.
**None of this is verified** — `ruff`, `mypy` and `lint-imports` alone say nothing wrong (mypy and
ruff read files directly off disk, not through the broken import path), but `pytest` — the thing
that actually proves the tables are correct — cannot exercise this code at all until the blocker is
fixed. Do not tick tasks.md section 3's first checkbox on the strength of this draft.

## Done (prior sessions — condensed; full detail in git history and `.handoff/log/`)

- Domain layer, application layer (all 6 SPEC-001 tasks.md section 2 items, merged to `develop` at
  `adce03d`), and SPEC-001 persistence Phase 0 (Alembic bootstrap, checkpoint-restart spike,
  ADR-0002, queue rewrite) — see `.handoff/log/2026-08-29-1929-claude.md` for full detail and every
  commit SHA; nothing here has changed.

## Next

1. **Decide how `revops` should resolve inside a worktree**, then have a human (not an unattended
   loop) apply it. Two real options, not exhaustive:
   - Reinstall editable **from the main checkout** normally (`pip install -e ".[dev]"`), and give
     future loop runs a **project-local `.venv`** instead of the global per-user site-packages —
     then each worktree gets its own `pip install -e ".[dev]"` inside its own `.venv`, cleanly
     isolated, no shared-state risk. Bigger one-time setup change.
   - Add a root `conftest.py` (`sys.path.insert(0, ...)` pointing at `sys.argv`/`__file__`-relative
     `packages/core`) as a deliberate, reviewed change — then add its path to
     `.handoff/AUTONOMOUS_QUEUE.md`'s always-allowed prefixes (alongside `.handoff/`, `.claude/`,
     `docs/playbooks/`, `scripts/`) so future loop runs don't halt on it. Smaller change, still
     shared-repo-wide, needs a real decision on whether that's the right permanent shape.
2. Once fixed, verified with a real `pytest` run of `tests/unit/infrastructure/persistence/test_models.py`
   from inside a fresh worktree (not the one from this run, which should be discarded once its draft
   is reviewed/reused) — then resume the loop at Item 1 with a clean gate-state reset.
3. Look at the `lint-imports` Windows `cp1252` `UnicodeEncodeError` noted above, independently of
   item 1 — it will hit again the moment any item's gate run needs `lint-imports` to actually report
   something (right now it's masked because the failure happens before it prints a real result).
4. Resume `.handoff/AUTONOMOUS_QUEUE.md` items 1-4 in order once (1) and (2) are done. Nothing about
   the plan, ADR-0002, or the queue's scope/ordering needs to change — this is a pure tooling
   blocker, not a design one.
5. Item 5 (LangGraph) is still untouched and still needs a fresh session, Opus, plan mode — unchanged
   from before this run.

## Gotchas

- **A git worktree does not see a global/per-user editable Python install.** `pip install -e` (this
  repo has never used a project-local `.venv` — confirmed no `.venv` in the repo, `uv` not on `PATH`)
  bakes an absolute path to the checkout it was run from into a PEP 660 finder in
  `AppData\Roaming\Python\Python312\site-packages`. Every worktree's copy of `packages/core/revops`
  is invisible to `pytest` (and therefore to `scripts/autonomous_gate.py`) until this is fixed for
  real — see `## Now` and `## Next` above. This blocks **every future worktree-isolated loop run
  that touches `packages/core/revops`**, not just this one.
- `mypy .` and `ruff check .` do NOT surface the above problem — they read the files being checked
  directly off disk rather than through the installed package's import path, so they will happily
  pass on worktree edits that `pytest` can never see. Don't trust a green `mypy`/`ruff` alone as
  proof that worktree code is real; `pytest` passing is the only proof that matters here.
- `lint-imports` crashes with a Windows `cp1252` `UnicodeEncodeError` from its `rich`-console
  renderer in at least one environment state (seen once, inside the worktree, cause not yet
  isolated — see `## Next` item 3).
- All gotchas from `.handoff/log/2026-08-29-1929-claude.md` (OneDrive/Defender git & filesystem
  interference, psycopg's Windows event-loop policy requirement, the checkpoint-table autogenerate
  trap, pre-commit unreliability, missing `__init__.py` in declared scope) still apply unchanged.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status                                          # main checkout: should still be clean, on feature/SPEC-001-persistence
git worktree list                                   # find .claude/worktrees/spec-001-persistence-loop and its branch
git log --oneline feature/spec-001-persistence-loop -5   # see the WIP commit(s) left there
docker compose ps                                   # confirm revops-postgres still healthy
```
Read `## Next` above before doing anything else. This is a tooling decision, not a design one —
do not re-derive ADR-0002 or re-plan the persistence layer, both are still correct.

## Open questions

- Which of the two `## Next` item 1 options (project-local `.venv` per worktree, vs. a permanent
  root `conftest.py`) does the user want? Needs the user — this is exactly the kind of environment
  decision with more than one defensible answer that an unattended loop should not pick on its own.
- Same open questions as `.handoff/log/2026-08-29-1929-claude.md`: OneDrive/Defender exclusion,
  provider keys not configured, `docs/tooling/RESEARCH.md` items still just-in-time.
