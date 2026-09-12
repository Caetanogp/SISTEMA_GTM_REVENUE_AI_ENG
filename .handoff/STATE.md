---
agent: codex
updated_at: 2026-09-12
branch: feature/SPEC-005-crm-attribution-model
spec: SPEC-005-crm-attribution-model
phase: "Approved spec and queue prepared; short pilot next"
status: in progress
---

# Current state

## Goal

Implement the PDF-aligned CRM attribution foundation: campaigns, touchpoints, source metadata,
opportunity status and complete account/contact interaction relationships, without starting RAG,
LLM, UI, analytics or agent-tool work.

## Now

SPEC-005 `spec.md`, `plan.md` and `tasks.md` are materialized and agreed. A new 11-item queue is
active in `.handoff/AUTONOMOUS_QUEUE.md`, limited to this spec's domain, application, persistence,
compatibility and verification work. The branch is `feature/SPEC-005-crm-attribution-model` and is
clean after commit `4b729b4 docs(spec-005): define CRM attribution foundation`.

The short pilot has not started. `python scripts/autonomous_gate.py` correctly returned exit 1
because Item 1 has not touched its declared domain/test evidence paths. No autonomous loop is
currently running.

## Done

- `4b729b4`: materialized the agreed SPEC-005 scope, implementation plan, 11-task checklist and
  replaced the historical SPEC-003 queue with a SPEC-005 queue.
- `codex.cmd --version`: `codex-cli 0.150.0`.
- `python scripts/check_agent_docs.py`: passed.
- `python scripts/check_pdf_traceability.py`: passed with 86 rows and pages 1-20 covered.
- Pre-commit hooks passed on the preparation commit.

## Next

1. Run a short pilot with the external Codex supervisor, capped to a small number of turns, and
   verify a real Item 1 commit plus the in-progress gate.
2. Inspect the pilot's branch diff, task evidence and gate output. Stop on `architecture_required`,
   `HUMAN_REQUIRED`, scope violation or Docker-dependent work that cannot be verified.
3. If the pilot is clean, launch the long supervisor run in the main checkout with the same queue.
4. After completion, run the full verify-before-done procedure before any merge or push.

## Gotchas

- Docker PostgreSQL is required for the migration round-trip and integration tests. The loop must
  stop if Docker is unavailable; it must not mark those tasks complete.
- The executor may not edit the queue, gate, supervisor, AGENTS.md, authorization artifacts or main.
- No agent pushes or merges. This branch must remain separate until the full gate is green.
- Product scope is fixed by SPEC-005. New statuses, attribution algorithms, external connectors or
  agent exposure require a deliberate scope change before implementation.

## Resume

```powershell
git status --short --branch
python scripts/autonomous_gate.py
powershell -ExecutionPolicy Bypass -File scripts/start_codex_loop.ps1 -MaxTurns 6
```

## Open questions

- None for the approved SPEC-005 pilot. Docker availability is an environment prerequisite, not a
  scope decision.
