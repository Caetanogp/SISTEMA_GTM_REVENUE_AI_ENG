# apps

Composition roots. Each app wires concrete adapters into use cases and exposes them.

- `api/` FastAPI: routers, request/response schemas, auth, RBAC, dependency wiring, SSE streaming,
  health checks, job enqueueing
- `worker/` Celery entrypoint and task registry (enrichment, batch scoring, scheduled follow-ups)
- `mcp/` MCP server exposing the CRM/RevOps tools under explicit contracts
- `web/` Next.js UI: CRM, pipeline, AI Assistant, HITL approvals, Agent Activity, dashboards

Apps may import every inner layer, but never each other. No business logic in a router or a task:
they parse input, call a use case, and format output.
