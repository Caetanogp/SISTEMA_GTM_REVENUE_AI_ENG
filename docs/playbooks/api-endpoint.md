# Playbook: add a FastAPI endpoint

`apps/api` is a composition root. A router parses input, calls a use case, and formats output.
Nothing else.

## Steps

1. **Request/response schemas** in `apps/api/schemas/` — Pydantic, `extra="forbid"` on requests.
   These are API contracts, separate from application DTOs even when they look identical today.
2. **Dependency wiring** in `apps/api/deps.py`: build the adapters, inject them into the use case.
   The router receives the use case, not a repository.
3. **Auth and RBAC** on every route. Resolve the current user, check the role, and pass
   `organization_id` down — tenant isolation belongs at the repository level, and the endpoint is
   where the tenant is established.
4. **Errors**: map domain exceptions to HTTP status codes in one place. Never leak a stack trace, a
   SQL string, or a provider error message to the client.
5. **Long work goes to the queue.** Sync is for short requests with an immediate answer; anything
   long-running, high-volume, or dependent on an external API is enqueued and returns a job id.
6. **Streaming**: SSE for agent progress. Do not open a WebSocket for one-directional updates.

## Testing

- Unit: the use case with fakes — that is where the logic is.
- Integration: `httpx.AsyncClient` against the app with real Postgres and Redis from docker compose.
  Cover 401, 403, 422 and the happy path.
- Never assert only on status codes: assert on the persisted state too.

## Checklist

- [ ] Request schema with `extra="forbid"`
- [ ] Auth + role check + `organization_id` propagated
- [ ] Router contains no business logic
- [ ] Domain errors mapped to status codes, no internals leaked
- [ ] Long-running work enqueued, not awaited inline
- [ ] Integration test covering auth failure and the happy path
- [ ] OpenAPI description accurate — it is documentation the demo shows
