# Working with coding agents on this repo

Distilled from the Claude Code team's own practices (Boris Cherny, Jan 2026) and adapted to this
project. Their framing is worth keeping: there is no single correct way to use these tools — the
setup is personal, and you should experiment. What follows is the default we start from.

## 1. Work in parallel

Run 3–5 git worktrees at once, one Claude session each. The team calls this the single biggest
productivity unlock.

```bash
git worktree add .claude/worktrees/<name> develop
cd .claude/worktrees/<name> && claude
```

Natural splits for this project: backend feature · front-end screen · evals/datasets · a dedicated
"analysis" worktree that only reads logs and runs queries. Name them, and add shell aliases to jump
between them.

## 2. Start every complex task in plan mode

Spend the effort on the plan so the implementation happens in one pass. Two habits from the team:

- have one session write the plan and a **second one review it as a staff engineer** — that is what
  our `staff-engineer-reviewer` subagent is for;
- the moment something goes wrong, **go back to plan mode and re-plan**. Do not keep pushing.

Use plan mode for verification steps too, not only for building.

## 3. Invest in the instruction files

After every correction, end with: *"update AGENTS.md so you do not make that mistake again."* The
model is unnervingly good at writing rules for itself. Edit these files ruthlessly over time and
keep iterating until the error rate measurably drops.

Keep them small — they are loaded every turn. Detail belongs in `docs/`, linked from
`AGENTS.md`. `scripts/check_agent_docs.py` enforces the budget.

## 4. Build your own skills and reuse them

If you do something more than once a day, turn it into a skill or a command. Ours live in
`.claude/skills/` (Claude) and `.codex/prompts/` (Codex), both thin wrappers over
`docs/playbooks/` — one text, two agents. Run `/techdebt` at the end of a session.

## 5. Let the agent debug on its own

Point it at the failure and say "fix this" — a failing CI run, a docker log, a stack trace. Do not
micromanage the *how*. It is unusually good at diagnosing distributed systems from logs, which will
matter once Celery workers and external APIs are in play.

## 6. Better prompting

- Challenge it: *"question me on these changes and do not open a PR until I pass your test."* Make
  the agent your reviewer.
- Ask it to prove things: *"prove this works"*, *"diff the behaviour between main and this branch."*
- After a mediocre fix: *"knowing everything you know now, throw this away and implement the elegant
  solution."*
- Write detailed specs and remove ambiguity **before** handing over the work. The more specific the
  input, the better the output — which is the whole premise of our SDD flow.

## 7. Terminal setup

Use `/statusline` so context usage and the current git branch are always visible. Colour-code and
name terminal tabs, one per task or worktree. Voice dictation produces longer, more detailed prompts
than typing — worth using for specs.

## 8. Use subagents

- Add "use subagents" to any request where you want more compute applied.
- Push individual tasks to subagents to keep the main context window clean and focused.
- Launch several `Explore` agents in parallel when mapping unfamiliar code.

Our roster is in `CLAUDE.md`.

## 9. Use the agent for data and analytics

Point it at a CLI, an MCP or an API and let it write the queries. For this project: `psql` against
the local Postgres, `docker logs`, and later CloudWatch. Analytical questions ("which campaigns
generate the highest-quality pipeline?") are a product feature here *and* a development habit.

## 10. Learn from it

- Turn on the Explanatory or Learning output style so it explains the *why* behind its changes.
- Ask for an HTML presentation to explain unfamiliar code — it makes genuinely good slides.
- Ask for ASCII diagrams of new protocols and code paths.

---

*Source: the Claude Code team thread of January 2026, plus the skills the user shortlisted:
`frontend-design`, `superpowers` (`/brainstorming`, `/systematic-debugging`), `mcp-builder`,
`skill-creator`. Adoption status for each: `docs/tooling/RESEARCH.md`.*
