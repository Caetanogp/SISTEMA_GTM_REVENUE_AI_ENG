---
agent: codex
updated_at: 2026-08-31
branch: feature/SPEC-003-deduplication
spec: SPEC-003-deduplication
phase: "SPEC-003 Item 5 complete; ready to implement the asynchronous scan worker."
status: spec-003-item-6-ready
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

1. Implement SPEC-003 Item 6: bounded asynchronous scan publication and processing in the worker.
2. Keep the Item 6 scope limited to queue/worker code and its unit/integration evidence.
3. Do not begin SPEC-004; the SPEC-003 queue remains active.

## Item 5 evidence (2026-09-01)

- Preparation/design commit: `34c7c6a` (`ADR-0006`, corrected queue scope, temporary-artifact
  isolation, and canonical resolver decision).
- Implementation commit: `56730cd` (`CanonicalRecordGroup`, typed account/contact persistence,
  canonical account reads, approval/task canonical writes, optional JSON/CSV phone, and ingestion
  canonical writes).
- Observed: `ruff check .` passed; `mypy .` passed with no issues in 125 source files; `lint-imports`
  passed; `pytest tests/unit -q` passed with 239 tests.
- Migration DDL was validated with `alembic upgrade 9a4e2c6d7f80:b7c9d1e2f304 --sql` and included
  typed candidate/alias tables, composite tenant FKs, partial active-alias indexes, event links,
  and staging phone. Live integration execution is pending a local database migration because the
  shared database is already stamped with the pre-correction schema; no destructive downgrade was
  run.
- The deterministic gate reports Item 6 as next and correctly requires `apps/worker/` and
  `tests/integration/` evidence. No long loop is running.

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

## Autonomous loop HALT (2026-08-31T06:54:44+00:00)

Item 4 declares scope ('packages/core/revops/infrastructure/persistence/', 'tests/unit/infrastructure/', 'tests/integration/'), but changes touch files outside it: ['packages/core/revops/application/ports.py', 'packages/core/revops/application/use_cases/deduplication.py', 'packages/core/revops/domain/entities/deduplication.py', 'tests/unit/application/use_cases/test_deduplication.py', 'tests/unit/domain/policies/test_deduplication.py']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-09-01T00:20:00+00:00)

Item 5 requires a deliberate application-boundary design before implementation. The approved plan
requires canonical alias resolution to be injected into existing ingestion, account-read, and task-
write use cases, but the current code has separate ingestion and agent unit-of-work contracts and
no defined shared resolver/composition contract for aggregated account reads. This choice affects
application ports, persistence adapters, and API composition. Stop and resolve the design before
continuing Item 5; no Item 5 implementation was started.

## Autonomous loop HALT (2026-08-31T07:01:59+00:00)

Item 4 declares scope ('packages/core/revops/infrastructure/persistence/', 'tests/unit/infrastructure/', 'tests/integration/'), but changes touch files outside it: ['pytest-of-Caetanogp123/pytest-0/test_active_tasks_file_rejects0/.handoff/AUTONOMOUS_QUEUE.md', 'pytest-of-Caetanogp123/pytest-0/test_active_tasks_file_rejects1/.handoff/AUTONOMOUS_QUEUE.md', 'pytest-of-Caetanogp123/pytest-0/test_active_tasks_file_rejects2/.handoff/AUTONOMOUS_QUEUE.md', 'pytest-of-Caetanogp123/pytest-0/test_active_tasks_file_uses_qu0/.handoff/AUTONOMOUS_QUEUE.md', 'pytest-of-Caetanogp123/pytest-0/test_active_tasks_file_uses_qu0/docs/specs/SPEC-999-example/tasks.md', 'pytest-of-Caetanogp123/pytest-0/test_write_report_writes_valid0/lead_scoring.json']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-09-01T00:06:26+00:00)

Item 4 declares scope ('packages/core/revops/infrastructure/persistence/', 'tests/unit/infrastructure/', 'tests/integration/'), but changes touch files outside it: ['pyproject.toml']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-09-01T00:09:20+00:00)

Item 5 declares scope ('packages/core/revops/application/', 'packages/core/revops/infrastructure/ingestion/', 'apps/api/', 'tests/unit/', 'tests/integration/'), but changes touch files outside it: ['UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_active_tasks_file_rejects0/.handoff/AUTONOMOUS_QUEUE.md', 'UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_active_tasks_file_rejects1/.handoff/AUTONOMOUS_QUEUE.md', 'UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_active_tasks_file_rejects2/.handoff/AUTONOMOUS_QUEUE.md', 'UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_active_tasks_file_uses_qu0/.handoff/AUTONOMOUS_QUEUE.md', 'UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_active_tasks_file_uses_qu0/docs/specs/SPEC-999-example/tasks.md', 'UsersCAETAN~1AppDataLocalTempcodex-revops-pytest-20264/test_write_report_writes_valid0/lead_scoring.json']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
