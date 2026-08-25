# .codex

Codex-side configuration for this repository.

- `config.toml` — execution posture (sandbox, approvals, network). No MCP servers enabled yet.
- `prompts/` — the same 12 skills Claude Code has, as Codex prompts. Each is a thin wrapper over
  `docs/playbooks/<name>.md`.
- `prompts/handoff-in.md` and `prompts/handoff-out.md` — the Codex equivalents of the Claude
  `/handoff-in` and `/handoff-out` commands.

Codex reads `AGENTS.md` at the repository root. That file is canonical for both agents: fix rules
there, never here.

Starting a session: read `.handoff/STATE.md` first (`prompts/handoff-in.md`).
Ending one: write it (`prompts/handoff-out.md`).
