# Harness Improvement: Faster, Shared Agent Development

- **Status:** agreed
- **Owner:** Codex and Claude Code maintainers
- **Created:** 2026-10-13
- **Classification:** repository development infrastructure; not a product feature

## Problem

Codex and Claude Code alternate in this repository and must follow the same development rules,
scope controls, and quality standards. The current autonomous gate repeats broad repository checks
after each executor turn, the queue can point at a stale spec, and a user away from the terminal
may not notice a stop. The gate and supervisor also need to preserve scope validation when advancing
between queue items. These issues can waste development time or reduce confidence in unattended
work.

## User stories

- As a maintainer, I want both Codex and Claude Code to use one verifiable gate contract so that
  alternating agents cannot bypass or reinterpret quality controls.
- As a maintainer, I want quick, informative feedback during incomplete work and comprehensive
  checks at defined completion boundaries so that iteration is faster without weakening the final
  quality bar.
- As a maintainer away from the terminal, I want a deduplicated Windows alert when the loop halts
  or completes so that I can respond without continuously polling the session.

## In scope

- The repository's agent instructions (`AGENTS.md` and its `CLAUDE.md` import), harness playbooks,
  autonomous queue contract, gate, Codex supervisor/launcher, harness tests, and a read-only Windows
  notification watcher.
- A shared, explicit verification lifecycle for Codex and Claude Code, including safe handling of
  incomplete turns, completed queue items, and final queue completion.
- Regression coverage for queue-item scope validation and gate-baseline advancement.
- Detection of queue/task/spec mismatch before execution begins.
- Durable gate baselines isolated by feature branch, active spec, and tasks-file identity, while
  preserving and safely migrating the existing untagged baseline only when queue/handoff metadata
  in its commit proves the same queue identity.
- Measurement and reporting of time spent in gate phases and executor/architecture turns, without
  recording secrets, prompts, or customer data.
- A pilot and comparative timing evidence before declaring a throughput improvement.
- Reconcile the existing queue's active-spec identity before using it for a later supervised run;
  queue preparation for SPEC-012 remains a separate operation after the shared contract is ready.

## Out of scope

- Any product feature, source code, API, schema, prompt, or runtime behavior under `apps/`,
  `packages/`, `evals/`, or product integration tests.
- Changes to product requirements, the project guide PDF, or product spec numbering/roadmap.
- Relaxing acceptance criteria, skipping required final checks, reducing security controls, or
  allowing either agent to authorize its own scope.
- Automatic resolution of `HUMAN_REQUIRED`, automatic merge/push, or automatic restart after a
  policy halt.
- New third-party dependencies, cloud services, or credentials.

## Acceptance criteria

1. Both Codex and Claude Code use the same gate semantics and cannot advance a task baseline until
   the completed item's required paths and declared scope have been validated. Regression tests
   cover committed and uncommitted changes at the item boundary.
2. The gate distinguishes intermediate progress, item completion, and full queue completion. The
   profile for each phase is deterministic and repository-controlled; the queue cannot supply an
   arbitrary shell command. Existing full verification remains mandatory before reporting goal
   completion.
3. A queue/task/spec mismatch is rejected before any executor turn, with a clear diagnostic and no
   mutation of gate baseline state.
4. Each gate phase and executor/escalation turn reports elapsed time. Timing output contains no
   prompts, credentials, tokens, or customer data and does not write generated files into the
   checkout.
5. A separate read-only watcher detects a new terminal halt/HUMAN_REQUIRED or goal-completion
   marker and emits at most one Windows notification per event. It cannot edit repository files,
   change gate state, resume a loop, or authorize work.
6. Focused harness tests cover shared gate behavior, phase selection, boundary validation, stale
   queue rejection, timing output, and watcher deduplication. Existing quality/security checks are
   not weakened.
7. A short pilot on a prepared feature queue records elapsed time and gate outcomes; any speedup is
   reported from measured data, not inferred from fewer checks.
8. Distinct queue identities never read or mutate one another's gate state. State records its
   identity and fails closed on mismatch; a legacy state is reused only when its saved baseline
   commit proves the same active spec, branch, and tasks file, using baseline handoff metadata for
   older queues that predate explicit queue identity fields.
9. A fixed `web-bootstrap` verification profile may be used only by queue item 1 when its declared
   scope includes `apps/web/`. Queue preflight may defer web configuration checks only when that
   bootstrap item is present; completion must require a valid npm manifest, lockfile, and non-empty
   `lint`, `test`, and `build` scripts, then run the same fixed lint, test, and build commands as
   `web`. A new queue baseline must not adopt an already-checked bootstrap item without verification.
   Without the bootstrap profile, existing `web` preflight behavior remains unchanged.

## Risks and open questions

- A faster intermediate phase could provide less feedback if it is underspecified. The plan must
  show which checks remain on every turn, item completion, and final completion.
- Gate-baseline advancement is security-sensitive. The old item's scope must be checked before the
  baseline moves, including for Claude Code, which does not use the Codex supervisor.
- Windows toast delivery depends on notification settings and an active user session. The watcher
  must report its own startup/health state and must not claim delivery when Windows rejects it.
- Timing data must remain operational metadata only; do not persist model prompts or raw executor
  output as part of this improvement.
- Queue-item sizing and phase selection should be validated against the SPEC-012 task checklist,
  but this harness spec must not change SPEC-012 requirements or product implementation.
