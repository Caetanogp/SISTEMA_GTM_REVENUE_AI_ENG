---
agent: codex
updated_at: 2026-08-30
branch: feature/SPEC-001-agent-graph
spec: SPEC-001-vertical-slice-account-prioritization
phase: "SPEC-001 Item 8 synthetic demo seed is complete; Item 9 is next."
status: item8-pilot-green
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

On `feature/SPEC-001-agent-graph`. Targeted verification is green after the LangGraph, API, and
security work: `ruff check` passed on the changed files, `python -m alembic upgrade head` applied
the runtime migration locally, `pytest tests/integration -q` passed (18 tests),
`pytest tests/adversarial -q` passed (3 tests), `bandit -r packages apps -q` is green with only
documented migration waivers, `gitleaks detect --no-git` is clean, and `pip-audit -l` in a clean
venv found no known vulnerabilities. The final `python scripts/autonomous_gate.py` also passed
all of its checks.

The policy/security work is implemented in the feature branch. The API composition root, JWT auth,
run/approval endpoints, adversarial coverage, and dependency audit now exist. The active SPEC-001
checklist has its first `## 7. Data and evals` checkbox complete; the remaining three data/evals
checkboxes and all four closeout checkboxes are still pending. The queue and `autonomous_gate.py`
now model those sections. The queue parser and gate were fixed and committed as `a356437`; the
implementation baseline was committed as `da756d6`.

Item 8 is complete on this branch and was committed as `c729380`. `python scripts/seed_demo.py` ran successfully twice
sequentially and twice concurrently after `alembic upgrade head`; both concurrent processes exited
0. The database contains exactly 1 demo organization, 1 user, 30 accounts, 30 contacts, 30
opportunities, and 60 interactions. Stable UUIDs plus a PostgreSQL transaction advisory lock make
repeated and concurrent invocations deterministic.

## Done (this spec; full narrative in `.handoff/log/2026-08-30-0106-claude.md`)

- SPEC-001 persistence remains merged on `develop`; this branch builds on that baseline with the
  graph runtime and resume wiring.
- The graph runtime now has `load_context`, `score_accounts`, `propose_action`, and
  `execute_action`, with a pooled Postgres checkpointer helper and a deterministic fake LLM for
  tests.
- The API layer now exposes `POST /agent/runs`, `GET /agent/runs`, `GET /agent/runs/{id}/stream`,
  and `POST /agent/runs/{id}/approve`, with token-based organization scoping.
- Approval decisions are now idempotent by persisted action id, and the audit/run history records
  run identity plus graph/prompt versions.
- The integration suite is green, including the repeated-resume idempotency case and the API
  happy path / auth failure coverage.

## Next

1. Implement and verify Item 9, the tool-selection eval dataset.
2. Execute Items 10-11 for the lead-scoring dataset and offline baseline, then complete closeout
   items 12-15.
3. Materialize the next spec only after SPEC-001 closeout; `docs/specs/` currently only contains
   SPEC-001 and roadmap placeholders.

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
- SPEC-002 and onward are roadmap placeholders only; there is no next `spec.md`/`plan.md`/`tasks.md`
  trio to hand to an unattended loop yet.
- The JWT helper now uses PyJWT instead of python-jose, which removed the `ecdsa` dependency from
  the project tree.
- The two earlier autonomous HALTs were caused by the queue parser/dirty pre-commit baseline and
  are resolved by commits `a356437` and `da756d6`; the current gate reaches Item 8 as expected.

## Autonomous loop HALT (2026-08-30T07:36:55+00:00)

Queue and tasks.md are out of sync - done_count is not covered by any item's closes range. Check every item's `- **Closes:** N tasks.md checkboxes` line adds up to tasks.md's total checkbox count for this section.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-08-30T07:37:33+00:00)

Item 8 declares scope ('scripts/', 'packages/core/revops/infrastructure/persistence/', 'tests/'), but changes touch files outside it: ['apps/api/__init__.py', 'apps/api/auth.py', 'apps/api/dependencies.py', 'apps/api/main.py', 'apps/api/routes/__init__.py', 'apps/api/routes/agent_runs.py', 'apps/api/runtime.py', 'apps/api/schemas.py', 'apps/api/settings.py', 'packages/core/revops/application/dto.py', 'packages/core/revops/application/ports.py', 'packages/core/revops/application/use_cases/decide_approval.py', 'packages/core/revops/application/use_cases/prioritize_accounts.py', 'packages/core/revops/application/use_cases/reason_about_accounts.py', 'packages/core/revops/domain/policies/task.py', 'packages/core/revops/infrastructure/agent/__init__.py', 'packages/core/revops/infrastructure/agent/checkpointer.py', 'packages/core/revops/infrastructure/agent/graph.py', 'packages/core/revops/infrastructure/agent/nodes.py', 'packages/core/revops/infrastructure/agent/prompt_loader.py', 'packages/core/revops/infrastructure/agent/prompts/prioritize_accounts.v1.md', 'packages/core/revops/infrastructure/agent/runner.py', 'packages/core/revops/infrastructure/agent/state.py', 'packages/core/revops/infrastructure/llm/__init__.py', 'packages/core/revops/infrastructure/llm/fake.py', 'pyproject.toml']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-08-30T07:38:29+00:00)

Item 8 declares scope ('scripts/', 'packages/core/revops/infrastructure/persistence/', 'tests/'), but changes touch files outside it: ['apps/api/__init__.py', 'apps/api/auth.py', 'apps/api/dependencies.py', 'apps/api/main.py', 'apps/api/routes/__init__.py', 'apps/api/routes/agent_runs.py', 'apps/api/runtime.py', 'apps/api/schemas.py', 'apps/api/settings.py', 'packages/core/revops/application/dto.py', 'packages/core/revops/application/ports.py', 'packages/core/revops/application/use_cases/decide_approval.py', 'packages/core/revops/application/use_cases/prioritize_accounts.py', 'packages/core/revops/application/use_cases/reason_about_accounts.py', 'packages/core/revops/domain/policies/task.py', 'packages/core/revops/infrastructure/agent/__init__.py', 'packages/core/revops/infrastructure/agent/checkpointer.py', 'packages/core/revops/infrastructure/agent/graph.py', 'packages/core/revops/infrastructure/agent/nodes.py', 'packages/core/revops/infrastructure/agent/prompt_loader.py', 'packages/core/revops/infrastructure/agent/prompts/prioritize_accounts.v1.md', 'packages/core/revops/infrastructure/agent/runner.py', 'packages/core/revops/infrastructure/agent/state.py', 'packages/core/revops/infrastructure/llm/__init__.py', 'packages/core/revops/infrastructure/llm/fake.py', 'pyproject.toml']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.
