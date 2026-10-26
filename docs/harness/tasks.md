# Harness Improvement Tasks

Tasks are ordered by dependency. This checklist covers repository development infrastructure only;
do not modify product code or product requirements.

## Shared gate correctness

- [x] Add regression tests proving a completed queue item's scope and required evidence are checked
  against its saved baseline before baseline advancement, for committed and uncommitted changes —
  verified by focused autonomous-gate tests.
- [x] Fix gate item-transition behavior so failed scope/evidence/verification leaves the old baseline
  unchanged and emits a precise halt — verified by state-preservation tests.
- [x] Validate queue metadata, task path, active spec identity, branch identity, item order, profile
  identifiers, and test-path roots before execution — verified by malformed/stale-queue tests.
- [x] Isolate durable gate state by branch/spec/tasks identity, preserve the legacy state unless its
  baseline commit proves it belongs to the active queue, and share the resolver with the Codex
  supervisor — verified by `pytest tests/unit/scripts/test_autonomous_gate.py
  tests/unit/scripts/test_codex_loop_supervisor.py -q` (83 passed), including isolation,
  legacy-resume, and identity-mismatch regression tests.

## Verification efficiency and parity

- [x] Implement deterministic progress-checkpoint, item-completion, and final-completion phases;
  only the gate chooses a phase — verified by phase-selection tests using task/baseline states.
- [x] Add the fixed verification-profile registry and safe argv construction for Python unit,
  integration, adversarial, docs, and web checks; reject arbitrary commands and incompatible paths —
  verified by allowlist/path-validation tests.
- [x] Add a first-item-only `web-bootstrap` profile that defers preflight until its completion,
  then requires the full web manifest/lockfile/scripts and runs fixed lint/test/build commands,
  rejects a pre-checked initial bootstrap baseline, and has regression coverage for bootstrap
  preflight, invalid completion, and successful completion; verified by
  `pytest tests/unit/scripts/test_autonomous_gate.py -q` (56 passed) and `pytest tests/unit -q`
  (552 passed).
- [x] Make Codex supervisor and Claude `/goal` consume identical gate semantics and report the same
  success/continue/halt outcomes — verified by supervisor contract tests and playbook examples.

## Diagnostics and alerts

- [x] Emit elapsed-time records for each gate phase/check and executor/architecture turn without
  prompts, raw responses, secrets, or PII — verified by output-schema tests.
- [x] Emit structured terminal events with stable IDs and finite event types from both gate and
  supervisor — verified by event-schema and duplicate-event tests.
- [ ] Implement a read-only foreground Windows watcher with toast/sound, deduplication, health and
  delivery-failure reporting — verified with mocked notifications and a manual Windows smoke test.

## Architecture model availability

- [x] Add quota-only fallback from `gpt-6.1-sol` to `gpt-6-astra` for architect/reviewer calls,
  preserve `xhigh`, record actual models, and cover quota exhaustion, non-quota errors, and fallback
  exhaustion — verified by `pytest tests/unit/scripts/test_codex_loop_supervisor.py -q` (38 passed),
  Ruff, format check, mypy, agent-doc check, and `git diff --check`.

## Validation and closeout

- [x] Update agent instructions and autonomous-loop playbook once to document the shared contract;
  keep `CLAUDE.md` importing `AGENTS.md` rather than duplicating rules — verified by
  `python scripts/check_agent_docs.py` and documentation review.
- [x] Run focused harness tests, then the full applicable `verify-before-done` checks; preserve all current
  quality/security checks — verified by recorded command output and clean-scope review.
- [ ] Run a short feature-queue pilot and record per-phase timings and outcomes; report speedup only
  if comparable elapsed-time evidence demonstrates one — verified by pilot artifact outside the
  checkout and handoff evidence.
