---
agent: claude-code
updated_at: 2026-08-25
branch: develop
spec: SPEC-001-vertical-slice-account-prioritization
phase: "0 — Domain & design (roadmap phase 0 of the project guide)"
status: ready-to-implement
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request → CRM context → read tool →
reasoning → proposed action → HITL approval → write tool → audit trail.

## Now

Nothing in flight. The engineering foundation is committed; SPEC-001 is written and not yet started.

## Done

- Repository foundation scaffolded on `develop` — Clean Architecture tree under `packages/core/revops/`
  (domain / application / infrastructure), apps split into `api`, `worker`, `mcp`, `web`.
  Evidence: `git log --oneline -1`, `tree -L 3`.
- `AGENTS.md` (canonical, 151 lines) + `CLAUDE.md` (63 lines, imports it with `@AGENTS.md`).
  Evidence: `python scripts/check_agent_docs.py` → passed.
- Handoff protocol and this file. Evidence: `.handoff/PROTOCOL.md`.
- Security layer: `docs/security/AGENT_SECURITY_RULES.md`, `.claude/settings.json` deny rules +
  hooks, `.pre-commit-config.yaml` with gitleaks and ruff.
- CI: `.github/workflows/ci.yml` (lint, types, import contracts, tests, secrets, SAST) and
  `evals.yml` (eval gate). `cd-staging.yml` / `cd-prod.yml` are documented stubs — no AWS account
  provisioned yet.
- 12 project skills + 12 playbooks + 8 subagents defined.
- `docs/tooling/RESEARCH.md`: MCP / plugin / CLI dossier. **Nothing installed yet** — awaiting the
  user's decision.

## Next

1. Install and validate the Python toolchain: `uv sync` (or `pip install -e ".[dev]"`), then confirm
   `ruff check .`, `mypy .`, `lint-imports` and `pytest tests/ -q` all run on the empty skeleton.
2. Write the domain layer for SPEC-001: `Account`, `Contact`, `Opportunity` entities and the
   `RiskLevel` / scoring value objects — pure Python, no frameworks.
3. Define the application ports and the `PrioritizeAccounts` use case, with unit tests against
   in-memory fakes.
4. Add the SQLAlchemy models and the first Alembic migration behind the persistence port.
5. Wire the FastAPI composition root and the first read tool (`search_accounts`), with an
   integration test.

## Gotchas

- `docker compose` must be up before `pytest tests/integration` — those tests hit real Postgres and
  Redis on purpose, and fail loudly rather than mocking the boundary away.
- The domain layer must not import Pydantic. `lint-imports` enforces this; use dataclasses there and
  keep Pydantic for application DTOs and tool schemas.
- The project guide PDF is the product source of truth, but it predates the Clean Architecture
  decision: its section 16 repo layout was superseded by ADR-0001.
- Windows host: run shell commands through Git Bash. Line endings are normalised to LF by
  `.gitattributes`.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git checkout develop && git pull
docker compose up -d
python scripts/check_agent_docs.py
cat docs/specs/SPEC-001-vertical-slice-account-prioritization/tasks.md
```

## Open questions

- Which MCP servers and plugins from `docs/tooling/RESEARCH.md` should be installed? Nothing has
  been installed so far, by design.
- LLM provider keys for local development are not set yet (`.env` does not exist). Needed before
  step 5 of `Next` can be tested end to end.
