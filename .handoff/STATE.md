---
agent: codex
updated_at: 2026-08-31
branch: feature/SPEC-003-deduplication
spec: SPEC-003-deduplication
phase: "SPEC-003 design approved; materializing spec, plan, tasks, and autonomous queue before implementation."
status: spec-003-planning
---

# Current state

## Goal

Ship the agentic GTM/RevOps platform's roadmap, spec by spec. SPEC-001 (vertical slice) and
SPEC-002 (lead/account ingestion) are both done and published; SPEC-003 is the active agreed spec.

## Now

On `feature/SPEC-003-deduplication`, created from published `origin/develop` at `67cd775`.
The user approved tenant-wide deterministic matching, admin-approved reversible logical aliases,
optional E.164 phone, asynchronous Celery scans, whole-record master selection, persistent
dismissal until data/policy change, and exact normalized matching without fuzzy or LLM behavior.

Filled a real gap before merging: `tasks.md`'s "map every acceptance criterion to evidence"
checkbox was ticked with no mapping actually recorded anywhere. Added the full 12-criterion table
to `docs/specs/SPEC-002-lead-account-ingestion/tasks.md`, verified by reading the cited code/test
bodies directly (not by trusting names) - gate re-confirmed green after.

`origin` is now configured (`https://github.com/Caetanogp/SISTEMA_GTM_REVENUE_AI_ENG.git`) -
new since the last session, not yet independently confirmed how/when. `develop` is also claimed
merged with SPEC-001 (commit `0407f8a`) and possibly pushed to `origin/develop` at `7e912c5` per
an earlier note in this file's history - worth confirming with `git log origin/develop` before
assuming it's live.

## Done (condensed; full multi-session narrative in `.handoff/log/2026-08-30-2319-mixed.md`)

- SPEC-001 (vertical slice): domain through closeout, merged into `develop`. Full detail:
  `.handoff/log/2026-08-30-0106-claude.md` and the 2026-08-30-2319 log.
- SPEC-002 (lead/account ingestion): domain, application, persistence, adapters, worker, API,
  security, closeout - all 15 queue items done and verified across several Claude Code and Codex
  sessions, including two real deliberate-design HALTs the loop correctly stopped for (application
  contract boundaries before Item 3/6). ADR-0005 records the Celery/outbox phasing decision.
  Full detail: `.handoff/log/2026-08-30-2319-mixed.md`.
- `scripts/autonomous_gate.py` was generalized to read whichever spec's `tasks.md` the active
  queue points at, and to run the full verify-before-done set (not just unit+architecture) once
  a queue is fully ticked.

## Next

1. Commit the approved SPEC-003 `spec.md`, `plan.md`, and `tasks.md` plus roadmap/handoff updates.
2. Replace `.handoff/AUTONOMOUS_QUEUE.md` with scoped SPEC-003 items and validate a pilot.
3. Implement inside-out: domain, application, persistence, ingestion compatibility, worker, API,
   security, and closeout. Do not begin SPEC-004.

## Gotchas

- `git checkout <branch>` can fail with `error: cannot stat '.claude': Invalid argument` when the
  target branch's `.claude/` tree differs from the current one.
- Never call `EnterWorktree` for this project - editable installs resolve to absolute paths from
  install time, so a worktree silently runs stale code.
- Always commit an item's own files *before* ticking its `tasks.md` box and re-running the gate -
  ticking first (in the same uncommitted tree) desyncs the gate's `baseline_sha` tracking from
  reality and causes a false scope-violation HALT on the *next* item.
- A ticked checklist box is not proof of work - this session found one (acceptance-criteria
  mapping) ticked with nothing behind it. Spot-check before trusting a checkbox at face value,
  especially right before a merge.
- `docs/playbooks/autonomous-loop.md` is the shared source of truth for unattended-loop rules,
  read identically by Claude Code and Codex.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline --decorate
python scripts/autonomous_gate.py
```

## Open questions

- OneDrive/Defender exclusion for this folder would likely remove the checkout gotcha, needs the
  user.
- Provider keys still not configured (`.env` does not exist) - the fake LLM gateway covers
  everything until then.
- `origin` remote and a possible `develop` push - confirm before assuming public state (see Now).
- SPEC-003's exact scope is not decided - see Next.

## Autonomous loop HALT (2026-08-31T00:00:00Z)

Stopped at SPEC-003 Item 4 before committing. The Item 3 application contract does not carry
organization_id on RecordAlias, while the tenant-scoped persistence port requires it for alias
creation; StartDeduplicationScan also needs an authenticated requested_by actor rather than a
tenant identifier. A deliberate contract redesign is required before persistence work can safely
continue. Item 4 changes are uncommitted draft work and must not be treated as complete.

## Deliberate design resolution (2026-08-31)

The Item 4 contract mismatch was resolved before resuming the autonomous loop. `RecordAlias` now
carries the explicit tenant `organization_id`, and scan creation receives authenticated
`requested_by` separately from the tenant. The persistence draft uses those values directly; no
tenant or actor identity is inferred. The loop launcher now allocates an ignored per-process pytest
basetemp instead of the OneDrive reparse-point cache. Unit tests and import architecture checks pass;
Item 4 still requires persistence and integration evidence.
