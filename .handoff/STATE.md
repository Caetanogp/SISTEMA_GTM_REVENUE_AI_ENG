---
agent: codex
updated_at: 2026-09-02
branch: feature/SPEC-003-deduplication
spec: SPEC-003-deduplication
phase: "Item 7 architecture escalation required before API implementation."
status: architecture-required
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

1. Complete the bounded read-only architecture review for the Item 7 application/persistence
   contracts before implementation resumes.
2. Authorize an Item 7 scope overlay only if the review selects a dominant, spec-conformant design.
3. Implement and test only the approved API and supporting-contract changes, then run the gate.

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

- Item 7 needs an architecture plan for a locked current-record fingerprint validation seam,
  established-master alias-group protection, and paginated deduplication-event history. These
  contracts are absent from the approved Item 7 API-only scope and must not be recreated in a
  FastAPI router.

## Gate observation (2026-09-02)

The first external authorization artifact was rejected for a UTF-8 BOM; after handoff cleanup, the
exact external rollover was approved from baseline `3214ed2` to `3ff6c2c`, covering 14 exact
supervisor-change paths. The ordinary gate then reported Item 7 pending because it has not yet
touched `apps/api/` and `tests/integration/`; no scope HALT remains.

## Pilot observation (2026-09-02)

The first pilot attempt stopped before the executor because `uv.lock` is not tracked by this
repository but was incorrectly required by the supervisor control snapshot. The supervisor was
corrected to snapshot only controls that exist in this checkout; no Item 7 implementation ran.

## Pilot observation (2026-09-02, executable resolution)

The second pilot stopped before the executor because Python could not resolve the Windows `codex`
alias (`WinError 2`), although `codex.cmd` is installed. The launcher now passes `codex.cmd`
explicitly; no Item 7 implementation ran.

## Gate observation (2026-09-02, authorization retry)

The rollover retry was rejected because its previous baseline SHA was mistyped. The exact gate
baseline is `92cfd4f5658d9c0e8cdb01b392105ec3acb25002`; no Item 7 implementation ran.

## Item 7 architecture observation (2026-09-02)

Direct inspection confirms the previously recorded gap remains: `MergeDeduplicationCandidate`
locks the candidate but has no port to lock/recompute the current member fingerprints or reject a
demoted established master with active aliases. `DeduplicationEventRepository` exposes only
idempotency lookup and append, so it cannot serve the specified paginated merge/revert history.
Correct implementation requires application and persistence changes outside Item 7's declared
`apps/api/`, `tests/unit/apps/`, and `tests/integration/` scope. No Item 7 implementation or task
checkbox change was made. Observed `python scripts/autonomous_gate.py`: exit 1, pending required
evidence paths `apps/api/` and `tests/integration/`.

## Pilot observation (2026-09-02, architect prompt encoding)

The executor correctly returned `architecture_required` and committed handoff-only evidence as
`0696c8b`. The architect process then rejected the Windows-locale prompt encoding before any
architecture decision. The runner now explicitly uses UTF-8 for subprocess input and output; the
pilot must resume from this clean checkpoint.
