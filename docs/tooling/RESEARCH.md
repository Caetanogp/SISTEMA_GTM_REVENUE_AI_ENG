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
| **superpowers** | `obra/superpowers`, MIT — third-party, distributed via the author's own catalog (`obra/superpowers-marketplace`), **not** Anthropic's `claude-code-plugins` marketplace | not Anthropic-curated (verified directly against `anthropics/claude-code/.claude-plugin/marketplace.json` — it is not listed there); trust signal is the author instead: identifiable maintainer (Jesse Vincent), MIT licence, active repo, thousands of stars, cross-agent support (Claude Code, Codex, Cursor, Gemini CLI) | **Installed** 2026-08-26, scope project. Brings `/brainstorming` (structured ideation before a spec) and `/systematic-debugging` (hypothesis → test → fix → verify). Both complement our SDD flow; brainstorming feeds `spec.md`. |
| **security-guidance** | `anthropics/claude-code` (official marketplace) | first-party (David Dworken, `dworken@anthropic.com`) — verified directly against `marketplace.json` | **Installed** 2026-08-26, scope project. Regex pattern warnings on Edit/Write, an LLM diff review on Stop, and an agentic commit-time reviewer (cross-file IDOR/auth-bypass/SSRF). Required Claude Code ≥ v2.1.144; updated from 2.1.126 first. Project rules fed into it: `.claude/claude-security-guidance.md`. |
| **mcp-builder** (skill) | `anthropics/skills` | official Anthropic skills repository | **Install at Phase 3**, when we build the MCP server that exposes the CRM/RevOps tools. Encodes how to design MCP tool contracts properly. |
| **skill-creator** (skill) | `anthropics/skills` | official | **Optional.** Useful when our own project skills need to grow beyond the current playbooks. |

Install commands, for reference (already run for the two above marked Installed):

```bash
/plugin marketplace add anthropics/claude-code
/plugin install frontend-design@claude-plugins-official
/plugin marketplace add https://github.com/obra/superpowers-marketplace   # not anthropics/claude-code
/plugin install superpowers@superpowers-marketplace
/plugin install security-guidance@claude-plugins-official
```

---

## MCP servers

| Server | Source | Stars | Verdict |
|---|---|---|---|
| **Context7** | `upstash/context7` | ~56k | **Install first.** Pulls current, version-correct documentation for LangGraph, FastAPI, SQLAlchemy, Pydantic v2 and Celery into context on demand. This project lives on fast-moving libraries where a model trained months ago will confidently write a deprecated API. Highest value-per-token of anything on this list. |
| **Playwright MCP** | `microsoft/playwright-mcp` | ~35k | **Install at Phase 1+**, when the Next.js UI exists. Drives a real browser through accessibility snapshots, so the agent can verify a screen actually works instead of assuming it does. Pairs with `frontend-design`. |
| **Semgrep MCP** | `semgrep` CLI, subcommand `semgrep mcp` | — (see caution) | **Caution — use the CLI subcommand, not the old package.** The standalone `semgrep/mcp` repo (the one most write-ups still cite, ~680 ⭐) was deprecated in Sept 2025 (Semgrep CLI v1.137.0): it is archived and no longer patched. Third-party forks of that archived repo exist on GitHub (`Szowesgad/mcp-server-semgrep`, `AmesianX/semgrep_mcp`) — do not install those; an unofficial fork of an abandoned security tool is exactly the kind of supply-chain risk §8 of the security rules warns about. If we adopt this, it must be the `semgrep mcp` subcommand shipped by the actively maintained `semgrep` CLI, with `SEMGREP_SEND_METRICS=off` set explicitly (the default sends pseudo-anonymised project metadata to Semgrep Inc.). The `semgrep` CLI in CI (already planned) covers the same scanning without this layer at all — install the MCP only if the interactive, mid-edit workflow proves worth the extra surface. |
| **Postgres MCP Pro** | `crystaldba/postgres-mcp` | ~2.8k | **Install at Phase 2**, read-only mode. `EXPLAIN` analysis, index tuning and database health checks — exactly what the pgvector retrieval work and the campaign analytics queries will need. Give it a restricted database role; never the migration user. |
| **GitHub MCP** | `github/github-mcp-server`, official | first-party | **Skip — disclosed attack, and no capability we actually need.** Invariant Labs disclosed a "toxic agent flow" in May 2025: a malicious public GitHub issue can hijack the agent into leaking private-repo data through a public PR, because a typical PAT spans every repo the user owns. GitHub calls it architectural, with no simple fix — mitigation is a single-repo, least-privilege token, not a patch. Our gitflow already forbids the agent from merging or pushing to `main`/`develop`; everything left (open a PR, check an Actions run, read a log) the `gh` CLI already does, at zero standing context cost and with no persistent connection to poison. Revisit only if a real need appears that `gh` cannot cover, and then only with a fine-grained PAT scoped to this one repository — never an org-wide or multi-repo token. |
| **Sentry MCP** | official Sentry | first-party | **Revisit at Phase 3**, once Sentry is actually wired up and there are real errors to triage. |
| **n8n MCP** | already in the user's Codex config | — | **Not for this project.** The whole point of this rebuild is that orchestration is code-first, not n8n. Leaving it connected only adds context noise and tempts the wrong architecture. |

### Security gate for MCP

| Tool | Source | Use |
|---|---|---|
| **mcp-scan** | `invariantlabs-ai/mcp-scan` (Invariant Labs, acquired by Snyk; also shipped as Snyk `agent-scan`) | Statically scans installed MCP servers for prompt injection in tool descriptions, tool poisoning, cross-origin escalation and rug-pull updates. Built by the same team that disclosed the GitHub MCP "toxic agent flow" below — the credential here is finding real MCP vulnerabilities, not just packaging a scanner. Thousands of stars, backed by an established security vendor since the Snyk acquisition, and integrated by third parties (Smithery AI uses it to protect hosted MCP servers). **Project rule: run it before installing any MCP server, and again after any MCP update.** |

```bash
uvx mcp-scan@<pinned-version>          # scan installed servers - pin it, this executes against your MCP config
uvx mcp-scan@<pinned-version> inspect  # list what each tool actually exposes
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
| 2026-08-26 | Context7 | `@upstash/context7-mcp` (npx, unpinned — see note) | **Installed**, scope `project` (`.mcp.json`, versioned) | Read-only docs lookup, lowest risk on the shortlist. `claude mcp add --scope project context7 -- npx -y @upstash/context7-mcp`. No API key set — works unauthenticated at a lower rate limit; add one later at `context7.com/dashboard` if that becomes a bottleneck. `npx -y` always resolves the latest published version — acceptable here since Context7 only reads documentation and executes no user-supplied input, but worth pinning (`@upstash/context7-mcp@<version>`) once it stabilizes. |
| 2026-08-26 | superpowers | `obra/superpowers-marketplace` (marketplace HEAD, unpinned) | **Installed**, scope `project` (`.claude/settings.json` → `enabledPlugins`) | Third-party (see the correction above — not Anthropic-curated). `claude plugin marketplace add https://github.com/obra/superpowers-marketplace` then `claude plugin install --scope project superpowers@superpowers-marketplace`. Note: `claude plugin marketplace add <owner/repo>` tries SSH first and fails without configured keys — use the full `https://` URL. On this machine, Git for Windows' bundled CA bundle couldn't validate GitHub's certificate over HTTPS either (`SSL certificate problem: unable to get local issuer certificate` — a stale/incomplete `ca-bundle.crt`, not a security-relevant block); fixed *without* disabling verification by pointing git at the Windows certificate store instead: `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.sslBackend GIT_CONFIG_VALUE_0=schannel` for that one command. Do not use `http.sslVerify=false` to work around this class of error. |
| 2026-08-26 | mcp-scan | package renamed to `snyk-agent-scan` (PyPI `mcp-scan` is now a redirect stub); current: `0.6.0` | **Not installed — needs a decision** | Confirmed via the maintained repo's README: a full scan now requires signing up at snyk.io and setting `SNYK_TOKEN`, a change from when this was researched as "free, no account." Correct command going forward: `uvx snyk-agent-scan@0.6.0 <path>` (pin the version), not `mcp-scan@latest`. Also note from the README: scanning an MCP config **executes** its stdio server to read tool descriptions — run it in a sandbox for untrusted configs, and expect an interactive per-server consent prompt. Creating the account is the user's call, not made unilaterally. Decided (2026-08-26): defer — what's installed so far (Context7, superpowers) is low blast-radius; revisit before adding a higher-risk MCP (Playwright, Postgres). |
| 2026-08-26 | security-guidance | official (`anthropics/claude-code` marketplace), David Dworken | **Installed**, scope `project` | Confirmed first-party by fetching `marketplace.json` directly (same check as the superpowers correction). Three layers: regex pattern warnings on Edit/Write (~25 known-dangerous patterns), an LLM diff review on the Stop hook, and an agentic commit-time reviewer that traces cross-file data flow (IDOR, auth bypass, SSRF). Required Claude Code ≥ v2.1.144 — this machine was on 2.1.126, the user ran `claude update` to 2.1.246 first. Data goes to `api.anthropic.com` under the same terms as Claude Code itself — a materially smaller trust expansion than a third-party MCP. `claude plugin install --scope project security-guidance@claude-plugins-official`. Project-specific rules fed into its review: `.claude/claude-security-guidance.md`. Real cost: an extra model call per turn with edits and per commit — `ENABLE_STOP_REVIEW=0` keeps only the commit-time review if that overhead matters. |
