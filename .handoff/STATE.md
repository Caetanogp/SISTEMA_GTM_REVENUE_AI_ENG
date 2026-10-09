---
agent: codex
updated_at: 2026-10-07
branch: feature/SPEC-010-research-and-outreach
spec: SPEC-010-research-and-outreach
phase: "SPEC-010 implementation and bounded closeout verification complete"
status: ready_for_merge
---

# Current state

## Goal

Implement bounded, tenant-safe company research and bilingual grounded follow-up preparation from
the approved PDF-aligned SPEC-010 scope, without sending messages or changing CRM records.

## Now

SPEC-010 implementation is complete on `feature/SPEC-010-research-and-outreach`. The v2 runtime
uses checkpointed selection, reservation, execution, and completion nodes; v1 resume behavior is
preserved. The approved closeout queue is complete. No overnight development loop is running or
needed for this spec because there are no remaining implementation tasks.

## Done

- Implementation commit: `c4ca593 feat(spec-010): checkpoint research runtime lifecycle`.
- Queue/closeout commit: `567eb3a docs(spec-010): add bounded closeout queue`.
- SPEC-010 scope, plan, ADR-0018, tasks, security boundaries, and PDF traceability are materialized.
- External research is disabled by default and only permits explicitly configured HTTPS company
  pages with bounded response/text/deadline limits, DNS/IP validation, no redirects, and no proxy
  trust.
- Follow-up drafts are bilingual, structured, evidence-referenced, and verifier-gated. No send,
  calendar, CRM mutation, or automatic sequence is in scope.
- Existing SPEC-009 v1 runs remain on the legacy graph composition; new runs use
  `single-agent-tool-runtime.v2`.

## Verification evidence

- Pilot: `pytest tests/integration/test_agent_runs_api.py tests/unit/infrastructure/agent/test_runtime_nodes.py tests/unit/application/use_cases/test_agent_tool_runtime.py -q` -> 15 passed.
- Unit: `pytest tests/unit -q` -> 467 passed.
- Integration: `pytest tests/integration -q` -> 47 passed, 3 known SQLAlchemy connection-cleanup warnings.
- Adversarial: `pytest tests/adversarial -q` -> 30 passed.
- Evals: `python -m evals.run --suite all` -> all 8 suites passed at 1.00; research and grounded-generation contracts are mandatory and green.
- Static/security: `ruff check .`, `ruff format --check .`, `mypy .` (188 files), `lint-imports` (4 contracts kept), `python scripts/check_agent_docs.py`, `python scripts/check_pdf_traceability.py` (86 rows), and `gitleaks detect --no-git` all passed.
- Docker integration dependency: Docker Server `27.5.1`, 2 containers running.

## Next

1. Run `python scripts/autonomous_gate.py` on the clean tree and record its final `GOAL ACHIEVED` output.
2. Run the complete `docs/playbooks/verify-before-done.md` command set once more if the gate requires it.
3. Review the feature diff against `develop`, then merge this feature branch into `develop` after user confirmation.
4. Publish `develop` only through the user's explicit `git push`; agents do not push.
5. Before any next autonomous loop, materialize and approve the next spec, plan, and tasks. Do not infer SPEC-011+ scope from the roadmap.

## Gotchas

- The PDF at `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf` remains the product
  source of truth.
- New research requires explicit authorized hosts and paths; an account domain alone never grants
  network access.
- Research content, CRM text, RAG passages, prior tool results, and model output are untrusted data.
  Tenant identity, permissions, risk, and HITL remain deterministic.
- The SPEC-010 queue is a bounded closeout queue, not an overnight feature-development queue. A
  long loop is appropriate only after a future approved spec has real unchecked implementation work.

## Resume

```powershell
Set-Location -LiteralPath "C:\Dev\SISTEMA_PORTFOLIO_AI_ENG"
git switch feature/SPEC-010-research-and-outreach
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

## Open questions

No product question is open for SPEC-010. Any architectural choice outside the approved plan
requires a deliberate design pass before coding.
