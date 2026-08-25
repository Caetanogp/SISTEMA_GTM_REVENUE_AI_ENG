# ADR-0001: Clean Architecture with LangGraph confined to infrastructure

- **Status:** accepted
- **Date:** 2026-08-25
- **Context spec:** SPEC-001

## Context

The project guide (section 16) proposes a layout organised by technical concern: `agent/graph`,
`agent/tools`, `agent/policies`, `data/models`, `workers/`. That layout is readable, but it puts the
agent framework at the centre of the codebase: business rules end up inside graph nodes, and the
system becomes a LangGraph application rather than a GTM/RevOps system that happens to use
LangGraph.

Two forces argue against that:

1. **This is a portfolio for AI Engineering roles.** Anyone can wire a graph. Demonstrating that the
   business logic survives a framework swap is a much stronger signal, and it is exactly what
   reviewers probe for.
2. **The agent framework layer is the fastest-moving part of the stack.** LangGraph in 2026 is not
   LangGraph in 2025. Rules about risk classification, deduplication and ICP scoring should not
   move when a framework does.

## Options considered

1. **The guide's layout as-is** — familiar, minimal ceremony, matches most LangGraph examples.
   Business rules end up in nodes and routers; testing a rule requires constructing graph state;
   a framework upgrade touches business code.
2. **Clean Architecture with strict layers** — domain / application / infrastructure / apps, with
   dependencies pointing inward and ports as the only crossing. More ceremony and some duplication
   (domain value objects and Pydantic DTOs), in exchange for framework-independent business rules
   that unit-test without any framework at all.
3. **Hexagonal-lite** — ports and adapters, but only around the database. Cheaper, but leaves the
   LLM and the graph tangled into the use cases, which is precisely where this system's risk lives.

## Decision

Option 2. Four layers, dependencies pointing inward:

```
apps → infrastructure → application → domain
```

- **domain**: entities, value objects, risk policies, scoring rules. Standard library only —
  no Pydantic, no SQLAlchemy, no LangGraph.
- **application**: use cases and ports (`typing.Protocol`), Pydantic DTOs, context builders.
- **infrastructure**: every adapter — SQLAlchemy, pgvector, the LangGraph graph, the LLM gateway,
  email, calendar, telemetry, Celery.
- **apps**: composition roots (`api`, `worker`, `mcp`, `web`).

**LangGraph is an adapter.** A node reads state, calls a use case, writes state. The decision about
whether an action is high risk lives in `domain/policies/risk.py` and is unit-tested with no graph
in sight.

The boundaries are enforced mechanically by `import-linter` contracts in `pyproject.toml`, run in CI
and in `tests/architecture/`. A rule that only exists in a README is a rule that erodes.

## Consequences

**Easier:** business rules are tested without a database, an LLM or a graph · a framework upgrade is
contained in one layer · the risk and policy logic — the part that matters for safety — is small,
pure and readable · the architecture claim is verifiable by a reviewer running one command.

**Harder:** more files and more indirection for a small feature · some duplication between domain
value objects and Pydantic DTOs · contributors used to framework-centric layouts need the layer
table in `AGENTS.md` before their first change.

**Cost accepted:** the extra indirection is real. For a system whose selling point is controlled,
auditable agent behaviour, keeping that control framework-independent is worth it.

**Revisit if:** the port indirection starts being routinely bypassed, or the duplication between
domain values and DTOs grows beyond a handful of types. Either would be evidence that the boundary
is drawn in the wrong place — which is a new ADR, not a quiet exception.

**Supersedes:** section 16 of the project guide, for repository layout only. The guide remains the
source of truth for product scope, roadmap and acceptance criteria.
