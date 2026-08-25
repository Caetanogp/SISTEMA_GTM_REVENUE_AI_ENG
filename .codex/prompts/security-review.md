# security-review

Run the agentic security review: prompt injection, tool safety, authorization, PII, secrets, dependencies and MCP. Use before merging anything that touches prompts, tools, context, auth, external calls or data.

Read `docs/playbooks/security-review.md` and follow it. That playbook is shared with Claude Code
(`.claude/skills/security-review/SKILL.md`) — edit the playbook, never the wrapper.

Project rules that always apply: `AGENTS.md`.
