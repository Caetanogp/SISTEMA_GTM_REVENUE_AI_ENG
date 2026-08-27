# CLAUDE.md

@AGENTS.md

Everything above applies. This file only adds what is specific to Claude Code.
**Do not duplicate rules here — edit `AGENTS.md`.**

## Working style

- Talk to the user in **Portuguese**; write repo content in **English**.
- Start every complex task in **plan mode** (shift+tab). Spend the effort on the plan so the
  implementation can happen in one pass. When something goes wrong, go back to plan mode and
  re-plan instead of pushing forward.
- Use plan mode for **verification** steps too, not only for building.
- Read `.handoff/STATE.md` at the start of a session and write it before ending one.
- After the user corrects you, update `AGENTS.md` (or the relevant playbook) so the same mistake
  cannot happen twice. This is expected, not optional.
- If you do something more than once a day, turn it into a skill or a command.

## Subagents (`.claude/agents/`)

Delegate to keep the main context clean, and to get an independent opinion:

| Agent | Use it for |
|---|---|
| `staff-engineer-reviewer` | reviewing a plan or a diff before implementation lands |
| `clean-architecture-guardian` | layer-boundary and coupling violations |
| `security-auditor` | prompt injection, secrets, scopes, PII, audit trail |
| `test-writer` | unit / integration / adversarial pytest suites |
| `eval-engineer` | golden datasets, scorers, thresholds, regression analysis |
| `db-schema-reviewer` | SQLAlchemy models, Alembic migrations, indexes, pgvector |
| `observability-engineer` | OTel spans, LangSmith traces, metrics, cost per run |
| `frontend-designer` | Next.js / shadcn screens |

Say "use subagents" when a task deserves more compute. Run several `Explore` agents in parallel
when mapping unfamiliar code.

## Skills (`.claude/skills/`)

`spec-feature` · `handoff` · `agent-tool` · `langgraph-node` · `api-endpoint` · `db-migration` ·
`eval-case` · `security-review` · `frontend-screen` · `adr` · `techdebt` · `verify-before-done` ·
`autonomous-loop`

Each is a thin wrapper over `docs/playbooks/<name>.md`, which Codex reads through
`.codex/prompts/`. Change the playbook, and both agents change with it.

## Commands (`.claude/commands/`)

- `/handoff-in` — load `.handoff/STATE.md` and restate goal, WIP and next steps
- `/handoff-out` — write `STATE.md` with evidence and snapshot it into `.handoff/log/`
- `/spec-new <slug>` — scaffold a new `docs/specs/SPEC-NNN-<slug>/`
- `/techdebt` — end-of-session sweep for duplication and dead code

## Parallel work

Use git worktrees for independent tracks (e.g. backend feature + frontend screen):

```bash
git worktree add .claude/worktrees/<name> develop
cd .claude/worktrees/<name> && claude
```

One worktree per task. Each session updates the shared `.handoff/STATE.md` only for the branch it
owns — never overwrite another track's section.
