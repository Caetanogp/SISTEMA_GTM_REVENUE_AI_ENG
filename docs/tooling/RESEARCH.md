# Tooling research: MCP servers, plugins, skills and CLIs

Researched 2026-08-25. **Nothing here is installed yet** — this is the dossier for the decision.
Star counts are from that date and are indicative, not exact.

## The policy that governs this list

Every MCP server you connect is (a) a permanent context cost on every turn and (b) an attack
surface: its tool descriptions are model-visible text written by a third party, and tool poisoning
is a real, demonstrated attack. So:

1. **Prefer a CLI over an MCP when both solve the problem.** `gh`, `gitleaks` and `semgrep` in the
   terminal cost nothing per turn and cannot inject anything into the context window.
2. Install an MCP only when it gives something a CLI cannot — live documentation, a browser, a query
   planner.
3. Before installing: check stars, maintainer, activity and licence; read what the tools do; run
   `mcp-scan` against the config.
4. Pin the version. Never `@latest` for something that executes code.
5. Record the decision in the table at the bottom of this file.

---

## Claude Code plugins

| Plugin | Source | Signal | Verdict |
|---|---|---|---|
| **frontend-design** | `anthropics/claude-code` (official marketplace) | first-party Anthropic, the most-installed Claude Code plugin | **Install.** This is the front-end skill worth having: it forces a design direction (typography, palette, spacing, motion) before coding, instead of the default AI-slop aesthetic. Directly useful for the Next.js CRM, the Agent Activity view and the dashboards. |
| **superpowers** | `obra/superpowers`, MIT, in the official marketplace since Jan 2026 | one of the most-starred plugins in the ecosystem; works with Claude Code, Codex, Cursor and Gemini CLI | **Install.** Brings `/brainstorming` (structured ideation before a spec) and `/systematic-debugging` (hypothesis → test → fix → verify). Both complement our SDD flow; brainstorming feeds `spec.md`. Cross-agent support matters here because we alternate Claude and Codex. |
| **mcp-builder** (skill) | `anthropics/skills` | official Anthropic skills repository | **Install at Phase 3**, when we build the MCP server that exposes the CRM/RevOps tools. Encodes how to design MCP tool contracts properly. |
| **skill-creator** (skill) | `anthropics/skills` | official | **Optional.** Useful when our own project skills need to grow beyond the current playbooks. |

Install commands, for when the decision is made:

```bash
/plugin marketplace add anthropics/claude-code
/plugin install frontend-design@claude-plugins-official
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

---

## MCP servers

| Server | Source | Stars | Verdict |
|---|---|---|---|
| **Context7** | `upstash/context7` | ~56k | **Install first.** Pulls current, version-correct documentation for LangGraph, FastAPI, SQLAlchemy, Pydantic v2 and Celery into context on demand. This project lives on fast-moving libraries where a model trained months ago will confidently write a deprecated API. Highest value-per-token of anything on this list. |
| **Playwright MCP** | `microsoft/playwright-mcp` | ~35k | **Install at Phase 1+**, when the Next.js UI exists. Drives a real browser through accessibility snapshots, so the agent can verify a screen actually works instead of assuming it does. Pairs with `frontend-design`. |
| **Semgrep MCP** | `semgrep` CLI, subcommand `semgrep mcp` | — (see caution) | **Caution — use the CLI subcommand, not the old package.** The standalone `semgrep/mcp` repo (the one most write-ups still cite, ~680 ⭐) was deprecated in Sept 2025 (Semgrep CLI v1.137.0): it is archived and no longer patched. Third-party forks of that archived repo exist on GitHub (`Szowesgad/mcp-server-semgrep`, `AmesianX/semgrep_mcp`) — do not install those; an unofficial fork of an abandoned security tool is exactly the kind of supply-chain risk §8 of the security rules warns about. If we adopt this, it must be the `semgrep mcp` subcommand shipped by the actively maintained `semgrep` CLI, with `SEMGREP_SEND_METRICS=off` set explicitly (the default sends pseudo-anonymised project metadata to Semgrep Inc.). The `semgrep` CLI in CI (already planned) covers the same scanning without this layer at all — install the MCP only if the interactive, mid-edit workflow proves worth the extra surface. |
| **Postgres MCP Pro** | `crystaldba/postgres-mcp` | ~2.8k | **Install at Phase 2**, read-only mode. `EXPLAIN` analysis, index tuning and database health checks — exactly what the pgvector retrieval work and the campaign analytics queries will need. Give it a restricted database role; never the migration user. |
| **GitHub MCP** | official GitHub | first-party | **Skip for now.** The `gh` CLI covers PRs, issues and CI runs at zero context cost. Revisit only if PR review becomes a bottleneck. |
| **Sentry MCP** | official Sentry | first-party | **Revisit at Phase 3**, once Sentry is actually wired up and there are real errors to triage. |
| **n8n MCP** | already in the user's Codex config | — | **Not for this project.** The whole point of this rebuild is that orchestration is code-first, not n8n. Leaving it connected only adds context noise and tempts the wrong architecture. |

### Security gate for MCP

| Tool | Source | Use |
|---|---|---|
| **mcp-scan** | `invariantlabs-ai/mcp-scan` (also shipped as Snyk `agent-scan`) | Statically scans installed MCP servers for prompt injection in tool descriptions, tool poisoning, cross-origin escalation and rug-pull updates. **Project rule: run it before installing any MCP server, and again after any MCP update.** |

```bash
uvx mcp-scan@latest          # scan installed servers
uvx mcp-scan@latest inspect  # list what each tool actually exposes
```

---

## CLIs (preferred, zero context cost)

| Tool | Job | Where it runs |
|---|---|---|
| `ruff` | lint + format | pre-commit, CI |
| `mypy` | static types | CI |
| `import-linter` | Clean Architecture layer contracts | CI, `tests/architecture/` |
| `pytest` | tests | CI |
| `gitleaks` | secret detection (fast, staged files) | pre-commit, CI |
| `trufflehog` | verified secret scan across history | periodic, manual |
| `semgrep` | SAST rulesets | CI |
| `bandit` | Python-specific security lint | CI |
| `pip-audit` | dependency CVEs | CI |
| `trivy` | container and IaC scanning | CI, Phase 5 |
| `gh` | PRs, issues, CI status | local |
| `docker compose` | local Postgres+pgvector and Redis | local |

The 2026 consensus stack for secrets is exactly this layering: gitleaks pre-commit and in CI,
trufflehog for verified history scans, plus GitHub push protection as the server-side backstop —
worth enabling once the repo is on GitHub.

---

## Decision log

Fill this in as things get installed, so the next agent knows what is connected and why.

| Date | Tool | Version | Decision | Reason |
|---|---|---|---|---|
| 2026-08-25 | — | — | Researched, nothing installed | Awaiting the decision on which to adopt |
| 2026-08-25 | Semgrep MCP | — | Corrected: not the `semgrep/mcp` repo | That repo is deprecated (Semgrep CLI v1.137.0, Sept 2025) and archived; unofficial forks of it exist and must not be installed. If adopted, use the `semgrep mcp` subcommand of the maintained `semgrep` CLI instead, with `SEMGREP_SEND_METRICS=off` set. |
