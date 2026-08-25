# application

Use cases and the contracts the outside world must satisfy.

**Contains:** use cases (PrioritizeAccounts, ResearchAccount, PrepareFollowUp, ApproveAction),
ports as `typing.Protocol` (AccountRepository, LLMGateway, EmailSender, KnowledgeRetriever,
AuditTrail), Pydantic DTOs, tool contracts and argument schemas, context builders and token budget.

**May import:** domain, Pydantic, the standard library.

**Must NOT import:** SQLAlchemy, LangGraph, FastAPI, httpx, redis, or any concrete adapter.

A use case orchestrates domain objects through ports. It never knows which database, which model
provider or which HTTP framework is on the other side. That is what makes it testable with fakes
and what keeps the agent logic independent of LangGraph.

Enforced by `lint-imports` and `tests/architecture/`.
