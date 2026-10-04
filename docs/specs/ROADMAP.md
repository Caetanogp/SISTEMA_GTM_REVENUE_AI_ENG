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
| [SPEC-003](SPEC-003-deduplication/) | 1 | normalize -> match -> merge -> master record -> preserve history, for contacts and accounts | done, merged into develop |
| [SPEC-004](SPEC-004-requirements-alignment/) | 0 | PDF traceability matrix, source-hash checker and mandatory offline eval gate | done |
| [SPEC-005](SPEC-005-crm-attribution-model/) | 1 | Campaigns, touchpoints, source attribution, opportunity status and complete interaction relationships | done, merged into develop |
| [SPEC-006](SPEC-006-llm-gateway/) | 1/3 | Own multi-provider gateway for OpenAI and Anthropic with routing, fallback, health, versions and cost metadata | done, merged into develop |
| [SPEC-007](SPEC-007-rag-ingestion/) | 2 | Versioned ICP, product, pricing, playbook, brand voice and policy corpus with pgvector ingestion | in progress |
| [SPEC-008](SPEC-008-context-retrieval/spec.md) | 2 | Task-scoped semantic retrieval with tenant-safe provenance and offline retrieval eval; hybrid/reranking and persistent memory remain deferred | draft, awaiting user review |
| SPEC-009-single-agent-tool-runtime | 2/3 | Bounded single-agent routing and up to five tool calls with explicit schemas and one-write/HITL rules | not started |
| SPEC-010-research-and-outreach | 2/3 | Grounded company research and personalized follow-up preparation | not started |
| SPEC-011-reply-intelligence | 2/3 | Reply classification, recommended next actions and feedback linkage | not started |
| SPEC-012-frontend-crm-assistant | 1/3 | Next.js CRM, assistant SSE, Agent Activity and HITL approval screens | not started |
| SPEC-013-mcp-server | 2/3 | MCP server exposing the CRM and RevOps tools with explicit contracts | not started |
| SPEC-014-observability | 3 | LangSmith, OpenTelemetry, Sentry and CloudWatch across API, graph and workers | not started |
| SPEC-015-evals-and-feedback | 3 | Full eval suite, safety datasets and in-product feedback regression loop | not started |
| SPEC-016-security-hardening | 3 | Injection defenses, RBAC, PII controls, quotas and explicit tool allowlists | not started |
| SPEC-017-high-risk-tools | 3 | Update CRM, `send_email` and `schedule_meeting` in sandbox/demo mode behind HITL | not started |
| SPEC-018-async-workers | 4 | Batch scoring, enrichment, research, scheduled follow-ups and eval workers | not started |
| SPEC-019-reliability | 4 | Outbox, DLQ, failed-operation storage, rate limits, circuit breakers and reconciliation | not started |
| SPEC-020-campaign-analytics | 3/5 | Campaign, funnel and revenue analytics with dashboard support | not started |
| SPEC-021-application-artifacts | 5 | App containers and immutable Git SHA/image digest artifacts | not started |
| SPEC-022-terraform-aws | 5 | IaC for ECS/Fargate, RDS, ElastiCache and Secrets Manager | not started |
| SPEC-023-cd-pipeline | 5 | Staging/production deployment, smoke checks, monitoring and demonstrated rollback | not started |
| SPEC-024-public-demo | 5 | Vercel/AWS demo, synthetic tenant, quotas, feedback and public deliverables | not started |
| SPEC-025-multiagent-evaluation | 6 | Compare single-agent V1 against a multi-agent split as an evidence-gated decision | not started |
| SPEC-026-multiagent-implementation | 6 | Supervisor plus specialist agents only if SPEC-025 demonstrates a real gain | **conditional** |

## Not spec'd here

Cross-cutting checklist items from the guide land inside whichever spec touches them rather than
getting their own number: Git SHA-based container versioning (SPEC-021/023), demo-mode quotas
(SPEC-024), and the offline eval CI gate (SPEC-004). Numbers and scope are deliberately not fixed.
