---
agent: codex
updated_at: 2026-09-12
branch: feature/SPEC-004-core-tools-reply-intelligence
spec: SPEC-004-core-tools-reply-intelligence
phase: "Design materialized; awaiting owner review before implementation."
status: agreed; implementation not started
---

# Current state

## Goal

Materialize and implement the bounded core agent tool runtime defined by SPEC-004 without expanding
into reply intelligence, multi-tool orchestration, or unattended architectural decisions.

## Now

SPEC-003 is complete and merged into local `develop`. SPEC-004 scope decisions are recorded:
English and Portuguese support; mandatory offline evals with optional live evals. The real
`spec.md`, `plan.md`, and `tasks.md` now exist in
`docs/specs/SPEC-004-core-tools-reply-intelligence/`. No production code has been changed.

The current branch is `feature/SPEC-004-core-tools-reply-intelligence`. Local `develop` remains one
commit ahead of `origin/develop` at `725a890` versus `6998b06`; no push was performed.

No autonomous development loop is running. The `.handoff/.autonomous_gate_state.json` file is
historical state from the previous pilot and is not evidence of an active loop.

## Done

- SPEC-003 closeout was verified before its local merge: `python scripts/autonomous_gate.py` reported
  `GOAL ACHIEVED: all queue items done, full gate green`; full unit, integration, adversarial, eval,
  architecture, documentation, and secret checks passed. The final integration result was 26 passed
  with three existing SQLAlchemy connection-cleanup warnings.
- SPEC-004 scope decisions were confirmed by the owner on 2026-09-12: five core tools, one tool per
  run, existing agent-run/SSE surface, bounded filters, canonical tenant-scoped context, email-only
  drafts, HITL for `create_task`, OpenAI `store=false`, English and Portuguese, offline eval required,
  live eval optional.
- SPEC-004 design documents were created in commit `dedb29c` and `ROADMAP.md` now links the agreed
  design. `python scripts/check_agent_docs.py` and `git diff --check` passed after the edits.

## Next

1. Owner reviews and approves `docs/specs/SPEC-004-core-tools-reply-intelligence/spec.md` and
   `plan.md`, especially the typed result/event contract.
2. Record the final result contract in an ADR or existing decision record, then begin the first
   unchecked task on this feature branch.
3. Implement domain and application contracts before infrastructure and API adapters, ticking
   `tasks.md` only with observed evidence.
4. Run the complete `docs/playbooks/verify-before-done.md` procedure before any merge or autonomous
   loop consideration.

## Gotchas

- Do not implement code until the owner approves the documents; this is required by the spec playbook.
- Reply intelligence is explicitly separate and out of scope for SPEC-004.
- Preserve the existing unit-of-work boundaries and agent-run approval/checkpoint path.
- Never push from an agent. `develop` integrates verified feature branches; `main` is hands-off.
- Do not use a worktree: the editable install resolves to absolute paths in the main checkout.

## Resume

```powershell
git status --short
git rev-parse --abbrev-ref HEAD
Get-Content docs/specs/SPEC-004-core-tools-reply-intelligence/spec.md
Get-Content docs/specs/SPEC-004-core-tools-reply-intelligence/plan.md
```

## Open questions

- Owner approval of the materialized SPEC-004 documents and the final typed result/event contract is
  still required before implementation.
