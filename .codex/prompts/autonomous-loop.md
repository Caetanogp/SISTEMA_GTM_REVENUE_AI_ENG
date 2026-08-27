# autonomous-loop

Run unattended development work against a pre-approved queue while the user is away. Use when
asked to set up, start, watch or stop a "night shift" / autonomous loop run.

Read `docs/playbooks/autonomous-loop.md` and follow it. That playbook is shared with Claude Code
(`.claude/skills/autonomous-loop/SKILL.md`) — edit the playbook, never the wrapper.

The queue it works from lives at `.handoff/AUTONOMOUS_QUEUE.md`; the judge of "done" is
`scripts/autonomous_gate.py`. Never trust a self-reported "finished" — trust the gate's exit code.

Project rules that always apply: `AGENTS.md`, specifically the "Autonomous loop mode" section.
