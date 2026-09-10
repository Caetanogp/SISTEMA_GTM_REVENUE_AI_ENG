---
agent: codex
updated_at: 2026-09-09
branch: feature/SPEC-003-deduplication
spec: SPEC-003-deduplication
phase: "Item 7 implementation after approved deliberate design pass."
status: in-progress
---

# Current state

## Goal

Complete SPEC-003 deduplication without moving product, security, or public-contract decisions into
an unattended loop.

## Now

SPEC-003 Items 1-6 are complete. Item 7 implementation is in progress after the approved deliberate
design pass. The API composition, scan dispatch/read contracts, domain policy, alias metadata, and
event-before-alias transaction ordering are implemented; concurrency revalidation and live
PostgreSQL evidence remain open.
pilot confirmed the executor correctly stops before implementation when application/persistence
contracts are missing.

Commits `8ec1e0c` through `e1b4609` contain the bounded supervisor, gate, Windows launcher fixes,
policy, ADR, tests, and pilot handoff evidence. The branch is not fully published after these
local commits; no push was performed.

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

1. Complete merge/revert stale-fingerprint, lock-order, event-reservation, and shared-master
   concurrency behavior required by the approved Item 7 design.
2. Add and run real PostgreSQL API, persistence, and concurrency integration coverage with Docker
   Desktop available; the current machine cannot connect to `dockerDesktopLinuxEngine`.
3. Add adversarial coverage, tick the two Item 7 task boxes only after evidence exists, then run the
   full `docs/playbooks/verify-before-done.md` procedure before considering a loop restart.

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

## Pilot result (2026-09-09)

The real pilot reached the executor, which returned `architecture_required` without Item 7 changes.
The first architect plan was revised by the reviewer; the second plan was also rejected after the
two-attempt limit. The supervisor then issued `HUMAN_REQUIRED` and stopped as designed.

The deliberate design pass resolved:

- Shared-master concurrency: repeated absorption into the same established master may serialize and
  succeed; competing demotion or alias reuse must produce one write and one `409`.
- Lock/replay ordering: persisted-event replay reads are non-locking; only the revert target event
  receives the ordered lock, avoiding event/alias deadlocks.
- Scan request identity: canonicalize `record_types` to a deterministic enum order before strict
  idempotency comparison, persistence, and publication.

The approved plan is recorded in `docs/specs/SPEC-003-deduplication/plan.md` and was tightened after
an independent review in commits `330cbbf` and `246c8b4`. Item 7's queue scope now includes the
application, domain policy, persistence, queue, API, worker, and test layers required by that plan.

## Implementation observation (2026-09-09)

Preparation commits `56c5e2c`, `7615ef6`, and `c648f78` aligned the queue, DTO/domain contracts,
scan dispatch, and deterministic candidate pagination. API commits `b1ca39e`, `4cfcfd3`, and
`eeb43d6` added admin-only scan, status, candidate, dismissal, merge, history, and revert routes;
`0cd0039` corrected event-before-alias ordering for foreign-key-safe merge/revert transactions.
Observed local evidence: `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`,
`python scripts/check_agent_docs.py`, and `pytest tests/unit -q` passed; 289 unit tests passed.
`python scripts/autonomous_gate.py` reports Item 7 quality green but correctly refuses completion
until its task checklist is ticked. The live integration command was not executable because Docker
Desktop was unavailable, so no integration success is claimed.

Docker Desktop was subsequently started. Against the isolated `DATABASE_URL` for
`revops_codex_spec003`, `python -m alembic upgrade head` passed, the Item 7 API/persistence checks
passed (`2 passed`), the real Celery/Redis worker check passed (`1 passed`), and the complete
integration suite passed (`24 passed`, with three existing SQLAlchemy connection-cleanup warnings).
 The shared `revops` database remains untouched because its legacy deduplication schema is not the
current migration shape.

The next transaction pass added PostgreSQL `add_if_absent` event reservation with
`ON CONFLICT DO NOTHING`, preserving the pre-lock replay check and preventing duplicate event
uniqueness errors from reaching the API. Focused deduplication integration passed again (`3 passed`)
against `revops_codex_spec003`; four existing deduplication use-case tests also passed. This is
still an intermediate checkpoint: merge/revert fingerprint revalidation, deterministic group locks,
and full `MergeEligibilityPolicy` orchestration are not yet complete.

The subsequent transaction pass completed locked canonical resolution, owning-account locks for
contact decisions, current fingerprint revalidation, and `MergeEligibilityPolicy` orchestration.
Merge and revert now reserve events before alias mutation. Observed complete local checks after this
pass: `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, `pytest tests/unit -q`
(`289 passed`), and isolated `pytest tests/integration -q` (`24 passed`, three existing ingestion
connection-cleanup warnings). The remaining closeout evidence is explicit concurrent/adversarial
coverage and acceptance-criteria mapping; Item 7 remains unticked and no long loop is authorized.

Closeout coverage was extended with an isolated two-session event-reservation race and adversarial
validation for invalid record types, duplicate inputs, and payload/idempotency-key disclosure.
Observed evidence: `pytest tests/adversarial -q` passed (`8 passed`) and the focused persistence
integration passed (`2 passed`) against `revops_codex_spec003`. The Item 7 checklist remains unticked
because end-to-end API authorization, pagination/replay, stale decision, and review-to-revert tests
still need to be added and observed before the full verify-before-done run.

## API closeout evidence (2026-09-09)

Added real PostgreSQL/ASGI coverage in `tests/integration/test_deduplication_api_flow.py:32` for
admin authorization and tenant-safe reads, pagination bounds, queued-scan visibility protection,
stale fingerprint rejection, merge, idempotent replay, merge history, and revert. The test exposed
and fixed a production composition bug in `apps/api/routes/deduplication.py:181`: merge now selects
the fifth service from the seven-service composition tuple.

Observed evidence on isolated `revops_codex_spec003`: `pytest tests/integration/test_deduplication_api_flow.py -q`
passed (`1 passed`); `pytest tests/unit -q` passed (`289 passed`); `pytest tests/integration -q` passed
(`26 passed`, three existing SQLAlchemy connection-cleanup warnings); `pytest tests/adversarial -q`
passed (`8 passed`); `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`,
`python scripts/check_agent_docs.py`, and `gitleaks detect --no-git` returned success. The two Item 7
API task boxes are now ticked in `docs/specs/SPEC-003-deduplication/tasks.md:28-29`.

## Next

Complete the remaining SPEC-003 closeout tasks: review the unmatched acceptance criteria, add the
required ADR/README operations update if still absent, map every acceptance criterion to observed
file-and-line evidence, run the full `docs/playbooks/verify-before-done.md`, and only then decide
whether the branch is ready for the supervised merge/loop transition. No long loop is authorized
by this checkpoint.

## Security and failure coverage evidence (2026-09-09)

Extended `tests/adversarial/test_deduplication_security.py:43` to reject untrusted PII fields in
administrative decision requests. Existing adversarial cases cover invalid/duplicate scan inputs
and history payload/idempotency disclosure; integration coverage covers tenant isolation, concurrent
event reservation, real worker delivery, bounded scans, stale decisions, merge replay, and revert.

Observed evidence: `pytest tests/adversarial -q` passed (`9 passed`); focused deduplication API,
persistence, and worker integration passed (`4 passed`) against `revops_codex_spec003`. Item 8
security and integration task boxes are now ticked in `docs/specs/SPEC-003-deduplication/tasks.md:33-34`.
