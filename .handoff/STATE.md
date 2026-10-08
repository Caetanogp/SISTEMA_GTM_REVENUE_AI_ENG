---
agent: codex
updated_at: 2026-10-07
branch: feature/SPEC-010-research-and-outreach
spec: SPEC-010-research-and-outreach
phase: "SPEC-010 implementation authorized; contracts and documents materialized"
status: in_progress
---

# Current state

## Goal

Implement bounded, tenant-safe company research and bilingual grounded follow-up preparation from the
approved PDF-aligned SPEC-010 scope, without sending messages or changing CRM records.

## Now

The active branch is `feature/SPEC-010-research-and-outreach` in `C:\\Dev\\SISTEMA_PORTFOLIO_AI_ENG`.
The scope, plan, tasks, and ADR are present and agreed. No implementation code or SPEC-010 queue has
been completed yet. Product decisions are fixed: authorized public company pages; English/Portuguese
email drafts; explicit source-unavailable limitations when CRM/RAG suffice; natural generation followed
by structured claim verification.

## Done

- SPEC-010 scope and PDF traceability are recorded in [spec.md](../docs/specs/SPEC-010-research-and-outreach/spec.md), [plan.md](../docs/specs/SPEC-010-research-and-outreach/plan.md), [tasks.md](../docs/specs/SPEC-010-research-and-outreach/tasks.md), and ADR-0018. These documents are unverified until the document checks run.
- Prior SPEC-009 was merged into `develop` at `9ec47e3`; the published handoff follow-up is `c23685c`. The historical SPEC-008 queue is not active for SPEC-010.

## Next

1. Implement domain/application contracts and focused tests for sources, claims, artifacts, and tools.
2. Implement the bounded research adapter, CRM/RAG context, generation/verifier, runtime checkpoints, and result API.
3. Add adversarial/eval coverage, create the scoped SPEC-010 queue, run the real pilot, and then run the full verification gate.

## Gotchas

- The PDF at `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf` remains the product source of truth.
- New research is disabled unless an organization explicitly configures authorized hosts and paths; an account domain alone does not authorize access.
- Research content, CRM text, RAG passages, prior tool results, and model output are untrusted data. Tenant identity, permissions, risk, and HITL remain deterministic.
- Existing SPEC-009 runs must keep v1 resume behavior; new SPEC-010 runs use the v2 lifecycle.
- Do not launch an overnight loop from the historical queue. A new SPEC-010 queue needs scoped items, clean baseline, pilot evidence, and gate approval.

## Resume

```powershell
Set-Location -LiteralPath "C:\Dev\SISTEMA_PORTFOLIO_AI_ENG"
git switch feature/SPEC-010-research-and-outreach
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

## Open questions

No product question is open for the approved SPEC-010 scope. Any architectural choice outside
`plan.md` requires a deliberate design pass before coding.
