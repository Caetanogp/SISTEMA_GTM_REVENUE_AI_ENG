---
name: security-review
description: Run the agentic security review: prompt injection, tool safety, authorization, PII, secrets, dependencies and MCP. Use before merging anything that touches prompts, tools, context, auth, external calls or data.
---

# security-review

Follow the procedure in `docs/playbooks/security-review.md` — read that file now and apply it.

It is the single source of truth for this workflow and is shared with Codex through
`.codex/prompts/security-review.md`. If the procedure needs to change, edit the playbook, not this wrapper.

Project rules that always apply: `AGENTS.md`.
