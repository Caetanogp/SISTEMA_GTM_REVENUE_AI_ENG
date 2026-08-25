# infrastructure

Concrete adapters. Every framework and every external system lives here, behind an application port.

**Suggested layout:**

- `persistence/` SQLAlchemy models, repositories, Alembic migrations
- `rag/` pgvector store, ingestion, chunking, retrieval
- `agent/` LangGraph graph, nodes, checkpointer, and `prompts/` (versioned files)
- `llm/` model gateway, routing, fallback, cost and token accounting
- `external/` email, calendar, research providers (sandboxed in demo mode)
- `queue/` Celery tasks and scheduling
- `telemetry/` OpenTelemetry, LangSmith, Sentry wiring

**May import:** domain, application, and any third-party library.

**Rule:** an adapter implements a port and translates. Business decisions do not happen here — if
you are writing an `if` about business meaning in this layer, it belongs in the domain.

Prompts are versioned files, not string literals in code: changing one bumps `prompt_version` and
requires re-running the eval suite.
