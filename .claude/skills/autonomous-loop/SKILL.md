---
name: autonomous-loop
description: Run unattended background development work against a pre-approved queue while the user is away. Use when asked to set up, start, watch or stop a "night shift" / autonomous loop run.
---

# autonomous-loop

Follow the procedure in `docs/playbooks/autonomous-loop.md` — read that file now and apply it.

It is the single source of truth for this workflow and is shared with Codex through
`.codex/prompts/autonomous-loop.md`. If the procedure needs to change, edit the playbook, not this
wrapper.

The queue it works from lives at `.handoff/AUTONOMOUS_QUEUE.md`; the judge of "done" is
`scripts/autonomous_gate.py`. Never trust a self-reported "finished" — trust the gate's exit code.

Project rules that always apply: `AGENTS.md`, specifically the "Autonomous loop mode" section.
