# Harness Improvement Plan: Faster, Shared Agent Development

- **Status:** approved; implementation in progress
- **Related scope:** `docs/harness/spec.md`

## Design goals

- One source of truth for Codex and Claude Code.
- Cheap feedback between meaningful verification boundaries, while retaining mandatory full
  verification at the end.
- Fail closed on stale queue metadata, scope mismatch, or invalid gate state.
- Keep the watcher outside the authority path: it observes and alerts but never controls execution.
- Measure before and after so performance claims are evidence-based.

## Proposed architecture

### Shared gate lifecycle

Keep `scripts/autonomous_gate.py` as the deterministic contract called by both the Codex supervisor
and Claude `/goal`. The gate derives its phase from the queue/task state rather than trusting the
executor to select a weaker mode:

1. **Progress checkpoint:** while the active task remains open, validate feature branch, queue
   syntax/identity, control integrity, changed-path scope, and required evidence. Run `git diff
   --check`; do not run repository-wide test suites. Report timings.
2. **Item completion:** when a task checkbox advances, identify the just-completed item from the
   saved baseline task count. Validate its paths and scope against its original baseline before
   moving that baseline. Then run the selected item profile plus shared static checks. Update
   baseline state only after all checks pass; on failure, retain the old baseline and halt with a
   repairable diagnostic.
3. **Goal completion:** when every queue item is complete, run the existing complete gate and the
   `verify-before-done` requirements. Only then return success.

Verification profiles are selected from this fixed registry in trusted harness code:

- `python-unit`: Ruff on changed Python files, `lint-imports` when package code changed, and the
  queue-declared pytest paths restricted to `tests/unit/` or `tests/architecture/`.
- `python-integration`: the same changed-file/static checks, plus pytest paths restricted to
  `tests/integration/`.
- `python-adversarial`: the same changed-file/static checks, plus pytest paths restricted to
  `tests/adversarial/`.
- `docs`: `git diff --check` and `python scripts/check_agent_docs.py`.
- `web`: fixed `npm run lint`, `npm test`, and `npm run build` commands from `apps/web`; the profile
  is invalid until the corresponding scripts and lockfile exist.
- `web-bootstrap`: allowed only on queue item 1 with `apps/web/` in scope. Preflight defers web
  configuration validation for the queue only when this item exists, allowing it to create the
  manifest and lockfile. At item completion it strictly validates the same manifest, lockfile, and
  `lint`, `test`, and `build` scripts as `web`, then runs the same fixed npm commands. Later `web`
  items retain strict validation at their completion boundary; queues without `web-bootstrap` keep
  the existing preflight requirement. A new gate-state baseline must reject a pre-checked bootstrap
  item so the first item's completion profile cannot be skipped.

The queue may choose a profile identifier and list test paths only. The gate validates profile/path
compatibility and constructs argument arrays; it never evaluates shell text from Markdown. Every
item profile also runs the shared `mypy .` and `lint-imports` checks when Python application/package
code is in scope. The final profile retains repository-wide formatting, lint, types, architecture,
unit, integration, adversarial, evaluations, documentation, and secret checks required by
`verify-before-done`.

### Queue identity and scope boundary

Extend queue metadata with an explicit active spec/task identity and an approved verification
profile plus test paths for each item. Validate the task file exists, matches the declared spec, and
corresponds to the feature branch before invoking either agent. The gate must retain the completed
item identity, scope, baseline, and task count until item verification passes. On a task transition,
use the prior item's saved baseline and scope for completion validation; do not silently rebase
first. A failed validation must leave the baseline unchanged and halt with a specific reason.

Gate state is selected by a stable digest of `(feature branch, active spec, tasks-file path)` and
stored in a separate ignored file for each queue identity. Persist the identity in each namespaced
state file and reject mismatches instead of silently initializing over them. Preserve the existing
`.handoff/.autonomous_gate_state.json` as a legacy state: reuse it only when its saved baseline
commit contains queue metadata matching the current identity, or older queue task metadata plus
handoff branch/spec metadata matching it; otherwise leave it untouched and initialize the
namespaced state. The Codex supervisor must resolve state through the same shared
gate function. Keep the legacy filename ignored and add an ignore rule for namespaced state files.

### Timing and pilot evidence

Measure elapsed time around executor turns, architecture/review calls, each gate phase, and each
individual check. Emit concise structured timing records to terminal output and supervisor artifacts
outside the checkout. Do not include prompts or raw model output in timing records. The pilot records
per-phase durations, total wall time, retries, and pass/fail status, then compares them with the
existing baseline where comparable measurements exist.

### Read-only Windows watcher

Add a small PowerShell watcher that observes structured terminal status events emitted by the shared
gate contract and Codex supervisor. Events have a stable ID and a finite type (`halt`,
`human_required`, or `goal_achieved`); the watcher deduplicates by ID without interpreting arbitrary
model text. It may emit a Windows toast and sound; it must not edit repository state, invoke the gate,
restart processes, or authorize scope. Provide a foreground mode first, with clear startup,
heartbeat, delivery failure, and shutdown messages.

## Files likely to change

- `scripts/autonomous_gate.py`
- `scripts/codex_loop_supervisor.py`
- `scripts/start_codex_loop.ps1`
- `.handoff/AUTONOMOUS_QUEUE.md` (contract/schema only; a SPEC-012 queue is prepared separately)
- `.codex/prompts/autonomous-loop.md`
- `docs/playbooks/autonomous-loop.md`
- `AGENTS.md` (and validate that `CLAUDE.md` continues to import it rather than duplicating rules)
- `tests/unit/scripts/test_autonomous_gate.py`
- `tests/unit/scripts/test_codex_loop_supervisor.py`
- New focused tests for the watcher and shared gate contract

No product source or product acceptance criteria should change.

## Testing and rollout

1. Add regression tests for the current gate-baseline/scope boundary before changing phase behavior.
2. Test every phase and queue-mismatch failure using temporary repositories/fixtures; prove that
   invalid transitions do not alter the baseline.
3. Test that Codex and Claude invocation paths select identical gate semantics.
4. Test watcher event deduplication and failure reporting without requiring live Windows toast
   delivery in CI; retain a manual Windows smoke test for actual toast behavior.
5. Run focused harness tests, then the full `verify-before-done` checks for harness changes.
6. Prepare a SPEC-012-specific queue separately, verify its baseline without resetting state, and
   run one short item pilot. Do not start a long loop until the pilot passes.
7. Add regression tests proving a stale legacy state remains byte-for-byte unchanged when a new
   queue identity starts, matching legacy state can resume, and namespaced identity mismatches halt.

## Trade-offs

- **Keep full checks after every executor turn:** simplest and most conservative, but repeats broad
  work and may slow iteration substantially.
- **Use deterministic phases (recommended):** reduces repeated broad checks while retaining strict
  scope checks and mandatory item/final verification. Requires careful boundary state and regression
  coverage.
- **Let the model choose checks:** rejected because the executor could omit the checks that expose
  its own mistakes.
- **Let the watcher restart or resume a loop:** rejected because alerts must not convert a halt into
  authorization or mask a policy boundary.

## Implementation guardrails

- The gate owns phase selection from trusted queue/task state. Neither executor may request a weaker
  profile.
- The item verification profile and paths are parsed as structured metadata, validated against the
  fixed registry and permitted test roots, and executed without a shell.
- The item baseline transition is transactional in behavior: validate old item scope/evidence,
  execute its profile, then persist the new baseline. Any failure leaves the old baseline intact.
- Claude `/goal` and the Codex supervisor call the same command and observe the same phase/result
  semantics. Codex may add process-level integrity checks, but they cannot replace shared gate
  checks.
