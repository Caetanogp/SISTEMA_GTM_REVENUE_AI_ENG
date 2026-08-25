# Agentic GTM & Revenue Operations Platform

A production-style agentic system for GTM / Revenue Operations: it reads CRM state, retrieves
context, researches accounts, prioritizes leads, proposes actions, **asks for human approval before
anything risky**, executes tools, and records an auditable, evaluable trail of everything it did.

Built code-first in Python — no low-code orchestrator — to demonstrate applied AI engineering end to
end: stateful agents, structured tool execution, RAG, evals, observability, security guardrails,
async workers, CI/CD and versioned deploys with rollback.

> **Status:** phase 0 complete (engineering foundation). Phase 1 — the vertical slice in
> [SPEC-001](docs/specs/SPEC-001-vertical-slice-account-prioritization/spec.md) — is next.

## Why it exists

The domain comes from a real B2B outbound system previously built and operated in production with
n8n. This is a from-scratch rebuild of that domain as a code-first agentic platform, with the
engineering practices the original could not express: measurable quality, controlled autonomy and
reproducible deploys. No customer data from that system is used here — the demo runs on a synthetic
tenant.

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy · Alembic · LangGraph · PostgreSQL + pgvector ·
Redis · Celery · MCP · Next.js + TypeScript + Tailwind + shadcn/ui · LangSmith · OpenTelemetry ·
Sentry · Docker · GitHub Actions · Terraform · AWS · Vercel

## Architecture

Clean Architecture, with dependencies pointing inward and enforced by `import-linter` in CI:

```
apps → infrastructure → application → domain
```

The business rules — risk classification, scoring, deduplication — are pure Python that runs without
a database, an LLM or a graph. LangGraph is an adapter, not the centre of the system
([ADR-0001](docs/decisions/ADR-0001-clean-architecture-and-langgraph.md)).

| Path | Layer |
|---|---|
| `packages/core/revops/domain/` | entities, value objects, risk and scoring policies |
| `packages/core/revops/application/` | use cases, ports, DTOs, context builders |
| `packages/core/revops/infrastructure/` | SQLAlchemy, pgvector, LangGraph, LLM gateway, providers, telemetry |
| `apps/{api,worker,mcp,web}` | composition roots |
| `evals/` `tests/` `infra/` `docs/` | evaluation suite, tests, IaC, documentation |

More: [docs/architecture/overview.md](docs/architecture/overview.md).

## Getting started

```bash
cp .env.example .env          # fill in what you need; never commit this file
docker compose up -d          # postgres+pgvector, redis
pip install -e ".[dev]"       # or: uv sync
pre-commit install
alembic upgrade head
uvicorn apps.api.main:app --reload
```

Checks:

```bash
ruff check . && mypy . && lint-imports && pytest tests/ -q
```

## How this repository is developed

Development alternates between two coding agents (Claude Code and Codex) as usage limits run out, so
the project treats agent continuity as infrastructure:

- **[`AGENTS.md`](AGENTS.md)** — canonical instructions for every agent. `CLAUDE.md` imports it, so
  the two can never drift apart (`python scripts/check_agent_docs.py` enforces that).
- **[`.handoff/STATE.md`](.handoff/STATE.md)** — the live development state. Read it first, write it
  last. `Done` entries require evidence: file:line, commit SHA, command output.
- **Spec Driven Development** — `docs/specs/SPEC-NNN-*/` holds spec → plan → tasks. No spec, no code.
- **Gitflow** — `feature/*` → PR → `develop` → `main`. Agents never commit on the protected
  branches; a hook and a pre-commit rule enforce it.
- **Security in three layers** — written rules, local enforcement (permission deny-lists, hooks,
  pre-commit) and CI (gitleaks, semgrep, bandit, pip-audit, an adversarial test suite).
- **Eval gate** — a change that degrades measured agent behaviour does not merge.

Shared procedures live once in `docs/playbooks/` and are exposed to both agents as skills
(`.claude/skills/`) and prompts (`.codex/prompts/`).

## Licence

MIT — see [LICENSE](LICENSE).
