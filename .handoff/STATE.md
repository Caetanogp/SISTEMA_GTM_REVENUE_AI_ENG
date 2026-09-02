---
agent: codex
updated_at: 2026-09-01
branch: feature/SPEC-003-deduplication
spec: SPEC-003-deduplication
phase: "Bounded architecture supervisor implemented; Item 7 real pilot pending."
status: in-progress
---

# Current state

## Goal

Complete SPEC-003 deduplication without moving product, security, or public-contract decisions into
an unattended loop.

## Now

SPEC-003 Items 1-6 are complete. Item 7 is next and no Item 7 implementation has started. Its
previous halt identified missing application/persistence contracts for stale merge validation,
master/alias protection, and history pagination.

Checkpoint commits `8ec1e0c` and `7f97b47` contain the supervisor, gate, launcher, policy, ADR,
tests, and the current handoff. The branch is published, but the external baseline rollover and
real Item 7 pilot have not been run.

The approved process change is implemented and committed: the economical Codex executor now
returns structured outcomes; a clean `architecture_required` invokes separate read-only
`gpt-5.6-sol/xhigh` architect and reviewer processes for at most two attempts. Approved plans get
an external item/baseline-bound scope overlay. Product, public-contract, dependency, destructive
migration, security, verification, external-action, dirty-worktree, and non-dominant choices remain
`HUMAN_REQUIRED`.

The independent first review found five launch/control issues. They are fixed: global CLI flags
precede `exec`, protected controls are hashed and checked before outcomes/gates, the launcher runs
from the selected checkout, baseline rollover requires an external exact-SHA authorization, and
authorization tests no longer depend on the OS temp location. The supervisor now also refuses a
temporary-directory fallback inside the checkout.

## Done

- Item 6 implementation commit `77c1815`: bounded idempotent Celery scans, retry behavior, queue
  failure visibility, and replay-safe candidate upserts. Observed isolated integration suite:
  23 passed.
- Supervisor focused checks observed on 2026-09-01: `ruff` and focused `mypy` passed; 46 focused
  tests passed both normally and with a repository-local pytest basetemp.
- Broad checks observed after the review fixes: `pytest tests/unit tests/architecture -q` passed
  with 287 tests; `lint-imports` kept all 4 contracts; `python scripts/check_agent_docs.py` passed;
  `ruff check .`, `ruff format --check .`, and `mypy .` passed (128 source files).
- Real CLI probes `codex --ask-for-approval never exec --help` and
  `codex --search exec --help` both exited 0. PowerShell launcher parsing passed.
- ADR-0007 records the bounded escalation decision and hard-stop policy.
- Checkpoint commit `8ec1e0c` passed pre-commit checks, including ruff, format, secret detection,
  agent-doc validation, and branch protection. Handoff commit `7f97b47` also passed its pre-commit
  checks.

## Next

1. Run a second independent review over the committed supervisor change when strong-model usage is
   available, resolving every actionable finding.
2. Create/apply the external exact-SHA baseline rollover and confirm the ordinary gate reports Item
   7 as pending rather than a scope HALT.
3. Run a short real Item 7 pilot and observe economical executor -> strong architect -> independent
   reviewer -> economical executor resume with no implementation diff before approval.
4. Only after that pilot succeeds, launch the long SPEC-003 loop. Do not begin SPEC-004.

## Gotchas

- Never use a worktree: the editable install resolves to absolute paths in the main checkout.
- Commit an item's implementation before ticking its `tasks.md` boxes; ticking first desynchronizes
  the gate baseline.
- The shared `revops` database has an obsolete pre-correction deduplication schema. Item 6 used the
  isolated migrated `revops_codex_spec003` database; no destructive downgrade was authorized.
- OneDrive/Defender can deny access to stale ignored temp directories. Current ignore/mypy rules
  exclude them, and the supervisor fails closed if `tempfile` resolves inside the repository.

## Resume

```powershell
git status --short
git rev-parse --abbrev-ref HEAD
pytest tests/unit/scripts/test_autonomous_gate.py tests/unit/scripts/test_codex_loop_supervisor.py -q
python scripts/autonomous_gate.py
```

## Open questions

- None before the supervisor review and pilot. A genuine hard-policy outcome from the pilot must be
  brought back to the user rather than inferred by the loop.

## Gate observation (2026-09-02)

The first external authorization artifact was rejected for a UTF-8 BOM; after handoff cleanup, the
exact external rollover was approved from baseline `3214ed2` to `3ff6c2c`, covering 14 exact
supervisor-change paths. The ordinary gate then reported Item 7 pending because it has not yet
touched `apps/api/` and `tests/integration/`; no scope HALT remains.

## Pilot observation (2026-09-02)

The first pilot attempt stopped before the executor because `uv.lock` is not tracked by this
repository but was incorrectly required by the supervisor control snapshot. The supervisor was
corrected to snapshot only controls that exist in this checkout; no Item 7 implementation ran.
