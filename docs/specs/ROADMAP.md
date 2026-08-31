# Spec roadmap

An index, not a commitment. Each row is a one-sentence placeholder for a spec that has not been
written yet, mapped to the phase and scope of `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf`
(sections 2 and 12). It exists so nobody has to re-derive "what comes next" from the PDF every
session -- it is not a substitute for the real `spec.md` -> `plan.md` -> `tasks.md` that gets
written when that item is actually about to start (`docs/playbooks/spec-feature.md`).

**Numbers and scope will shift.** A later spec can split, merge, or reorder once we know more from
implementing the one before it -- that is expected, not a deviation. Phase 6 (multi-agent) is
explicitly evidence-gated in the guide: SPEC-017 is a decision point, not a green light to build
SPEC-018.

Update this file when a spec starts (mark it and link the folder), when scope genuinely changes
enough to reorder what follows, or when a new item is discovered mid-implementation.

| Spec | Phase | One-liner | Status |
|---|---|---|---|
| [SPEC-001](SPEC-001-vertical-slice-account-prioritization/) | 1 | Vertical slice: NL request -> CRM context -> read tool -> reasoning -> proposed action -> HITL -> write tool -> audit trail | done, merged into develop |
| [SPEC-002](SPEC-002-lead-account-ingestion/) | 1 | CSV/JSON import with async synthetic enrichment | done, merged into develop |
| [SPEC-003](SPEC-003-deduplication/) | 1 | normalize -> match -> merge -> master record -> preserve history, for contacts and accounts | agreed |
| SPEC-004-core-tools-reply-intelligence | 1 | Remaining read/write tools from the risk matrix (`search_accounts`, `get_pipeline_metrics`, `prepare_followup`) + structured reply classification | not started |
| SPEC-005-frontend-crm-assistant | 1 | Next.js CRM, AI Assistant (SSE streaming), Agent Activity and HITL approval screens | not started |
| SPEC-006-rag-ingestion | 2 | pgvector + versioned ingestion for ICP, product docs, playbooks, brand voice | not started |
| SPEC-007-context-builder-retrieval-evals | 2 | Per-task context assembly with a token budget; retrieval measured separately from generation | not started |
| SPEC-008-mcp-server | 2/3 | MCP server exposing the CRM/RevOps tools with explicit contracts (`apps/mcp`) | not started |
| SPEC-009-observability | 3 | LangSmith + OpenTelemetry + Sentry wired through API, graph and workers | not started |
| SPEC-010-eval-suite-feedback-loop | 3 | Full eval suite (lead scoring, reply classification, tool selection, RAG, safety) + in-product feedback feeding the regression dataset | not started |
| SPEC-011-security-hardening | 3 | Prompt injection suite, RBAC, PII controls -- tested against real running code, not just the governance rules already in place | not started |
| SPEC-012-high-risk-tools | 3 | `send_email`, `schedule_meeting` behind sandboxed demo mode and an outbound allowlist | not started |
| SPEC-013-redis-celery-workers | 4 | Harden and expand workers for batch scoring and scheduled follow-ups | not started |
| SPEC-014-reliability-patterns | 4 | Retry/backoff, dead-letter queue, rate-limit coordination, idempotency under load | not started |
| SPEC-015-terraform-aws | 5 | IaC for ECS/Fargate, RDS, ElastiCache, Secrets Manager | not started |
| SPEC-016-cd-pipeline-activation | 5 | Turn `cd-staging.yml`/`cd-prod.yml` from stubs into real versioned deploys with demonstrated rollback | not started |
| SPEC-017-public-demo | 5 | Vercel frontend, synthetic tenant, quotas/rate limits, in-product feedback live | not started |
| SPEC-018-multiagent-evaluation | 6 | Evals comparing single-agent V1 against a multi-agent split -- a decision point, not an implementation | not started |
| SPEC-019-multiagent-implementation | 6 | Supervisor + Research/Qualification/Outreach/CRM Operations agents | **conditional** -- only if SPEC-018 shows a real gain |

## Not spec'd here

Cross-cutting checklist items from the guide (section 17) that land inside whichever spec touches
them at the time, rather than getting their own number: Git SHA-based container versioning
(part of SPEC-016), demo-mode quotas (part of SPEC-017), the eval CI gate (already active in
`.github/workflows/evals.yml`, strengthened in SPEC-010).
