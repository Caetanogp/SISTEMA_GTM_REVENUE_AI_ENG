---
agent: codex
updated_at: 2026-10-22
branch: fix/agent-web-bootstrap-profile
spec: Harness Improvement: Faster, Shared Agent Development
phase: "web bootstrap profile implemented, verified, and committed locally"
status: in_progress
---

# Current state

## Goal

Improve the shared Codex/Claude Code development harness without changing product behavior.

## Now

Current follow-up (2026-10-22): branch `fix/agent-web-bootstrap-profile` is based on
`origin/develop`. The approved harness extension adds `web-bootstrap`, restricted to queue item 1
and `apps/web/` scope. When present, queue preflight defers web configuration checks so the first
item can create the frontend; bootstrap completion still requires a valid manifest, lockfile, and
`lint`/`test`/`build` scripts and runs the fixed npm commands. Later web items are still verified
strictly at item completion. The existing `web` profile behavior is unchanged when no bootstrap
item is declared. Design, plan, and task checklist were updated to match the approved contract. No
product code, queue, pilot, or autonomous loop was touched. Commit
`69b96004eb32d29fb70a96493ad6357cf921a82b` contains the implementation. The focused gate suite
passed 56 tests; `pytest tests/unit -q` passed 552. `ruff check .`, `ruff format --check .`, `mypy .`,
`lint-imports`, `python scripts/check_agent_docs.py`, `gitleaks detect --no-git`, and
`git diff --check` passed. Integration, adversarial, and eval suites were not run because only the
harness gate and its tests/docs changed. The autonomous gate itself was intentionally not run
because the repository queue is still the historical SPEC-011 queue and is not bound to this
branch.

The SPEC-012 approved documents and the user's `.mcp.json` change are preserved in stash
`SPEC-012 approved docs and local MCP config before web bootstrap harness work`; older SPEC-012
stashes remain untouched. Nothing was pushed or merged. The earlier harness initiative history
below predates this focused follow-up.

### Earlier Harness Context

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
web uses fixed npm commands and rejects missing scripts or lockfiles. Gate state now uses a stable
digest of branch/spec/tasks identity, stores that identity in namespaced ignored files, and fails
closed on mismatch. The legacy `.handoff/.autonomous_gate_state.json` is reused only when baseline
queue/handoff metadata proves the same identity. The real SPEC-011 legacy state was recognized as
matching SPEC-011 and was not modified during that read-only check. The Codex supervisor and Claude
`/goal`/`/loop` now share the
documented exit contract (0 success, 1 continue, 2 halt, any other exit invalid); the supervisor
classifies outcomes through the gate helper and cannot report a halt as pilot success. Timing output
contains fixed phase/check names, duration, and outcome only. Gate and supervisor terminal events use
UUID IDs, finite types, and no free text; the read-only PowerShell watcher validates and deduplicates
them, with mocked-notification coverage. Its explicit Windows test-notification command returned 0
without delivery errors, but the agent cannot confirm that the toast was visually received.
Applicable `verify-before-done` checks passed after this change: Ruff, format (278 files), mypy (204
files), import contracts (4 kept), `pytest tests/unit` (546 passed), agent-docs, Gitleaks (no leaks),
and `git diff --check`. Focused gate/supervisor tests passed (83); focused Ruff, format, and mypy
passed. Integration/adversarial/eval suites were not run because no product adapters, database code,
prompts, tools, or evals changed. New regression tests cover state isolation, legacy preservation,
legacy resumption, and fail-closed identity mismatch. Commit `ee8cd7dfd1f0bfbb509dc34a19b89e8e53c7d6f6`
contains this change. The Windows toast test command returned 0, but
visual receipt remains unconfirmed. The SPEC-012 pilot was not run because this harness branch
cannot satisfy the SPEC-012 feature-branch queue. Eleven of thirteen harness checklist items are
complete; toast receipt and the short pilot remain.

PR #2 for `fix/agent-harness-efficiency` is open at
`https://github.com/Caetanogp/SISTEMA_GTM_REVENUE_AI_ENG/pull/2`. Its frontend build,
lint/types/architecture, and test checks passed. The Secrets and SAST job failed only at
`pip-audit`: the existing `requirements-ci.txt` pins `certifi==2026.7.22` and
`virtualenv==21.14.7`, which now have known advisories. These pins were unchanged by the harness
branch and are also present in `origin/develop`.

The isolated remediation was merged through PR #3 at `cafea6091886ebef906f2701353689854754d0b5`.
It updates only the two CI pins to `certifi==2026.10.19` and `virtualenv==21.14.9`.
`pip-audit --strict --no-deps -r requirements-ci.txt` returned `No known vulnerabilities found`;
all five PR #3 checks passed. The harness branch now includes the updated `origin/develop` via a
merge commit and was pushed as head `60ca4724cd9b648ce9cbdb44ee7e22779a84a9ca`. Its refreshed CI
run `39858705388` passed all four CI checks, including Secrets and SAST. PR #2 remains open and
mergeable; no merge has been performed yet.

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

1. Review this committed branch and decide whether to publish/open a PR; it has not been pushed or
   merged.
2. After this change is integrated, return to the SPEC-012 prep branch and restore its approved
   documents and `.mcp.json` from the named stash. Then prepare a queue using `web-bootstrap` for
   item 1, preserve the historical SPEC-011 gate state, and run one short item pilot before any
   overnight loop.
3. Separately, confirm whether the earlier Windows watcher test notification appeared; do not
   weaken event validation to address delivery.

## Gotchas

- Use `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`; the OneDrive clone is stale.
- Set `PYTHONPATH` to `packages\core;<repo root>`, plus UTF-8 environment variables, for local
  Python checks. This avoids the global editable install pointing into OneDrive.
- Never delete or reset `.handoff/.autonomous_gate_state.json`. It is the historical SPEC-011 state;
  another queue identity gets a separate ignored file and leaves it untouched.
- Docker Compose services in this checkout are not running. Use uniquely named disposable
  containers and loopback-only dynamic host ports for verification; leave unrelated containers and
  volumes untouched.
- SPEC-012 documents remain in preserved stashes from branch switches. The latest is
  `SPEC-012 approved docs before per-queue gate state implementation`; apply that named stash when
  returning to `feature/SPEC-012-frontend-crm-assistant`. Earlier snapshots remain preserved.
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
