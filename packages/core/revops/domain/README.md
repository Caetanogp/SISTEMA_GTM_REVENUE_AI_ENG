# domain

The innermost layer. Business truth about GTM/RevOps, expressed as pure Python.

**Contains:** entities (Account, Contact, Opportunity, Campaign, Touchpoint, AgentRun),
value objects (Score, RiskLevel, EmailAddress, Domain), domain services (deduplication rules,
ICP scoring rules, risk classification), domain errors.

**May import:** the Python standard library. Nothing else.

**Must NOT import:** Pydantic, SQLAlchemy, LangGraph, FastAPI, httpx, redis, or any other layer.
No I/O, no network, no database, no clock, no randomness that is not injected.

Use `@dataclass(frozen=True)` for value objects and plain classes for entities. If a rule needs
data from outside, it takes it as an argument: the domain never fetches anything.

Enforced by `lint-imports` (see `pyproject.toml`) and `tests/architecture/`.
