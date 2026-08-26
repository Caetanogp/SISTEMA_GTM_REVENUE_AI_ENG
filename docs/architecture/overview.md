# Architecture overview

Product scope, roadmap and acceptance criteria: the project guide PDF in `docs/`.
Layer rules: `AGENTS.md`. Why the layers are drawn this way: `docs/decisions/ADR-0001`.

## Runtime shape

```
Next.js (Vercel)
      │  HTTPS / SSE
      ▼
FastAPI  ──────────────► Redis ──► Celery workers
  │  auth, RBAC, validation        enrichment, batch scoring,
  │  enqueue, streaming            scheduled follow-ups, evals
  ▼
LangGraph  (stateful, checkpointed, interruptible)
  │
  ├─► Policy / guardrails   schema → domain rules → authz → risk
  ├─► Tools / MCP           CRM read/write, research, email, calendar, analytics
  └─► Context builder       CRM state + RAG + tool outputs, under a token budget
      │
      ▼
PostgreSQL + pgvector       business state, audit trail, RAG, evals, feedback
      │
      ▼
Observability               LangSmith traces · OpenTelemetry spans · Sentry · CloudWatch
```

## Value flow

```
user request
  → retrieve CRM context
  → retrieve relevant knowledge (RAG)
  → research / enrich if needed
  → score and prioritize
  → propose a plan
  → validate structured action
  → apply policy + permissions
  → HITL if high risk or low confidence
  → execute tool
  → persist business state + audit trail
  → expose trace and metrics
  → collect feedback
```

Feedback and failed runs become eval cases after human triage. That loop — deploy, trace, feedback,
eval, improve — is the point of the system, not a nice-to-have.

## Code layout

| Layer | Path | Holds |
|---|---|---|
| domain | `packages/core/revops/domain/` | entities, value objects, risk and scoring policies |
| application | `packages/core/revops/application/` | use cases, ports, DTOs, context builders |
| infrastructure | `packages/core/revops/infrastructure/` | SQLAlchemy, pgvector, LangGraph, LLM gateway, external providers, telemetry, queue |
| apps | `apps/api`, `apps/worker`, `apps/mcp`, `apps/web` | composition roots |

Dependencies point inward and are enforced by `lint-imports`.

## Memory, deliberately separated

| Kind | Where | Example |
|---|---|---|
| Thread / short-term | LangGraph checkpoint | last steps, pending approvals, tool outputs |
| Business state | PostgreSQL | contacts, opportunities, tasks, interactions |
| Long-term knowledge | pgvector + document store | playbooks, ICP, product docs |
| User/org preferences | PostgreSQL, scoped and consented | brand voice, default policies |

Conflating these is the most common way agentic systems become unexplainable.

## Versioning

Every run records what produced it: `graph_version`, `prompt_version`, model config, RAG corpus
version, eval dataset version, Git SHA and image digest. A failure has to be reproducible from the
`agent_runs` row alone — that is what makes rollback a decision rather than an archaeology project.

## Phasing

0 domain & design → 1 code-first MVP (SPEC-001) → 2 RAG + context → 3 production AI engineering
(observability, evals, security) → 4 async + scale → 5 cloud + CI/CD → 6 multi-agent, only if evals
justify it.

Full spec-by-spec index: `docs/specs/ROADMAP.md`.

Single-agent until the data says otherwise. Multi-agent is the last step, not a requirement for
calling V1 done.
