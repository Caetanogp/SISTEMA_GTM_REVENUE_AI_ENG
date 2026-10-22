---
agent: codex
updated_at: 2026-10-22
branch: fix/agent-harness-efficiency
spec: Harness Improvement: Faster, Shared Agent Development
phase: "harness implementation and applicable verify-before-done checks passed; watcher receipt and pilot pending"
status: in_progress
---

# Current state

## Goal

Improve the shared Codex/Claude Code development harness without changing product behavior or code.

## Now

SPEC-011 is merged into `develop` as PR #1. This dedicated `fix/agent-harness-efficiency` branch is
based on `origin/develop`. The harness-only scope and plan are approved, and
`docs/harness/tasks.md` contains the ordered checklist. Implementation has started with the shared
gate transition and regression tests. The draft covers shared gate semantics for Codex and Claude
Code, safe verification phases, stale-queue rejection, timing evidence, and a read-only Windows
watcher. It excludes all product source and
requirements. The SPEC-012 working documents remain safely preserved in the stash
`WIP SPEC-012 docs before dedicated harness branch` on `feature/SPEC-012-frontend-crm-assistant`.

The autonomous gate now validates a completed item's scope, required evidence, and quality profile
against the saved baseline before advancement. It rejects counter regressions/jumps, preserves the
baseline on failed scope/evidence/verification, and requires a clean worktree before advancing.
Codex supervisor retains a scope authorization through the gate transition so it can validate the
just-completed item, then clears it. Queue validation binds active spec, task path, and branch;
checks sequential item numbers, checkbox totals, fixed profile identifiers, and compatible existing
test-path roots. Gate phase selection is deterministic: open work runs only staged/unstaged diff
hygiene, a checkbox transition verifies the completed item before moving baseline, and full queue
completion runs the full gate. Fixed verification profiles build command argv in trusted code:
Python profiles run Ruff on changed Python files, mypy/import-lint when application/package Python
changes, and pytest only on profile-authorized paths; docs runs diff checks and the docs validator;
web uses fixed npm commands and rejects missing scripts or lockfiles. Test fixtures keep gate state
outside their temporary Git checkouts. The Codex supervisor and Claude `/goal`/`/loop` now share the
documented exit contract (0 success, 1 continue, 2 halt, any other exit invalid); the supervisor
classifies outcomes through the gate helper and cannot report a halt as pilot success. Timing output
contains fixed phase/check names, duration, and outcome only. Gate and supervisor terminal events use
UUID IDs, finite types, and no free text; the read-only PowerShell watcher validates and deduplicates
them, with mocked-notification coverage. Its explicit Windows test-notification command returned 0
without delivery errors, but the agent cannot confirm that the toast was visually received.
Applicable `verify-before-done` checks passed: Ruff (278 files), format (278 files), mypy (204
files), import contracts (4 kept), `pytest tests/unit` (540 passed), agent-docs, Gitleaks (no leaks),
and `git diff --check`. Integration/adversarial/eval suites were not run because no product adapters,
database code, prompts, tools, or evals changed. Focused harness tests passed (91); targeted mypy,
docs check, and the PowerShell mocked-notification/dedup smoke also passed. Ten checklist items are
complete; visual toast confirmation and the SPEC-012 short pilot remain.

## Done

- CI run `38283929452` at `9a77a81b827f8406fe7e32dc1b437558eadba89b`: passed quality, security,
  unit, integration, and adversarial jobs, including locked mypy 2.4, Semgrep, Bandit, and pip-audit.
- Eval run `38283929458` at the same commit: passed all 11 suites and PDF traceability.
- CI run `38327449741` and Eval run `38327449728` on published commit `923111b`: both passed;
  Semgrep, Bandit, dependency audit, integration, adversarial, eval, and PDF traceability passed.
- PR #1 was merged into `develop` on 2026-10-13 as `d7a8876b6766f3b857fed7aed13d3aba47174888`.
- Review fixes: `reply_runtime.py` checkpoints provider failure as fixed `provider_failure` and never
  stores arbitrary exception text; `reply.py` persists the matching run thread id. Regression
  evidence: `pytest tests/unit/infrastructure/agent/test_reply_runtime.py -q` passed 5 tests and
  `pytest tests/integration/test_reply_api.py -q` passed 3 tests using the explicit C:\Dev checkout.
- Refreshed local gate: `python scripts/autonomous_gate.py` exited 0 with
  `GOAL ACHIEVED: all queue items done, full gate green.` Ruff, mypy, import contracts, pytest,
  docs, formatting, integration, adversarial, evals, and Gitleaks all reported OK. It used
  disposable PostgreSQL/Redis containers on loopback-only dynamic ports; both containers were
  stopped and auto-removed. The standalone integration suite also passed 52 tests.
- The frontend workflow's setup/build steps were skipped because `apps/web/package.json` is absent;
  no frontend build result is claimed.
- Local authoritative checkout `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`: `pytest tests/unit
  tests/architecture -q` passed 508 tests with repository `PYTHONPATH` set.
- Read-only gate scope probe at baseline `af0f0df`: exactly 17 violations and no missing evidence;
  the approved reconciliation names those exact files.
- `python scripts/check_pdf_traceability.py`: passed, 86 rows and pages 1-20.
- `bandit -r packages apps -q`: exit 0 (existing Bandit comment warnings only).
- `pip-audit --strict --no-deps -r requirements-ci.txt`: exit 0, no known vulnerabilities.
- `run_quality_gate(full=True)`: all 10 checks passed, including unit, integration, adversarial,
  evals, and Gitleaks.
- `python scripts/autonomous_gate.py`: exit 0 with `GOAL ACHIEVED: all queue items done, full gate
  green.` Ruff, mypy, import contracts, unit/architecture, docs, format, integration, adversarial,
  evals, and Gitleaks all reported OK.
- Disposable PostgreSQL and Redis verification containers were removed by exact name; no volumes
  were created. Existing stopped development containers were untouched.

## Next

1. Confirm the clearly labeled Windows watcher test notification appeared. If so, close the watcher
   acceptance item; if not, investigate delivery without weakening event validation.
2. Restore/prepare the separate SPEC-012 queue from its approved source, validate its baseline
   without resetting gate state, and run one short item pilot. Do not start an overnight loop before
   the pilot passes.

## Gotchas

- Use `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`; the OneDrive clone is stale.
- Set `PYTHONPATH` to `packages\core;<repo root>`, plus UTF-8 environment variables, for local
  Python checks. This avoids the global editable install pointing into OneDrive.
- Never delete or reset `.handoff/.autonomous_gate_state.json`; the 8-item baseline must remain
  unchanged.
- Docker Compose services in this checkout are not running. Use uniquely named disposable
  containers and loopback-only dynamic host ports for verification; leave unrelated containers and
  volumes untouched.
- The SPEC-012 working tree was stashed by name before creating this branch. Return to
  `feature/SPEC-012-frontend-crm-assistant` and apply only the named stash when resuming that work.
- `.handoff/AUTONOMOUS_QUEUE.md` still contains the historical SPEC-011 queue and is not bound to
  this harness branch. The new gate rejects it as stale; do not run the real gate until a queue
  matching the active spec and feature branch is prepared.

## Resume

```powershell
Set-Location -LiteralPath 'C:\Dev\SISTEMA_PORTFOLIO_AI_ENG'
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

## Open questions

No product scope decisions are part of this harness initiative. The queue verification profile
registry and watcher event contract are defined in the approved plan and tasks.
