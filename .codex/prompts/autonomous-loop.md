# autonomous-loop

Run unattended development work against a pre-approved queue while the user is away. Use when
asked to set up, start, watch or stop a "night shift" / autonomous loop run.

Read `docs/playbooks/autonomous-loop.md` and follow it. That playbook is shared with Claude Code
(`.claude/skills/autonomous-loop/SKILL.md`) — edit the playbook, never the wrapper.

The queue it works from lives at `.handoff/AUTONOMOUS_QUEUE.md`; the judge of "done" is
`scripts/autonomous_gate.py`. Never trust a self-reported "finished" — trust the gate's exit code.

Codex runs are controlled by `scripts/codex_loop_supervisor.py`. The normal executor handles one
item per process. A technical design gap returns the structured `architecture_required` outcome
before any implementation; the supervisor then invokes a read-only strong-model architect and a
separate reviewer. `HUMAN_REQUIRED` remains a hard stop. Never edit the queue, supervisor, gate,
policy, or external authorization artifact from an executor turn.

Project rules that always apply: `AGENTS.md`, specifically the "Autonomous loop mode" section.
