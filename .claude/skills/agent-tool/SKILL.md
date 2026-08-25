---
name: agent-tool
description: Add a new agent tool with its Pydantic schema, risk level, allowlist entry, port/adapter, validation chain, audit row, tests and eval case. Use when the agent needs a new capability that touches the CRM or the outside world.
---

# agent-tool

Follow the procedure in `docs/playbooks/agent-tool.md` — read that file now and apply it.

It is the single source of truth for this workflow and is shared with Codex through
`.codex/prompts/agent-tool.md`. If the procedure needs to change, edit the playbook, not this wrapper.

Project rules that always apply: `AGENTS.md`.
