# Playbook: autonomous loop ("night shift")

How to run unattended development work — Claude working alone, on a pre-approved queue, while the
user is away from the computer. Grounded in Anthropic's own loop engineering taxonomy
([claude.com/blog/getting-started-with-loops](https://claude.com/blog/getting-started-with-loops)):
our case is **goal-based** — a task with a verifiable exit criterion, evaluated by a separate
process rather than the model's own say-so.

## The three pieces

1. **`.handoff/AUTONOMOUS_QUEUE.md`** — the only source of work. Ordered items, each with a
   declared file scope and a verifiable done criterion. One item is marked
   `HALT: PLAN-MODE-REQUIRED` when it needs real architectural judgment — the loop stops there,
   it does not attempt it.
2. **`scripts/autonomous_gate.py`** — the referee. Never trust the model's own "I'm done" — this
   script decides, deterministically: `exit 0` (goal achieved), `exit 1` (keep going), `exit 2`
   (HALT — wrong branch, scope violation, the next item needs a human, or too many consecutive
   failures on the same item). On `exit 2` it writes the reason to `.handoff/STATE.md` itself.
3. **`/goal`** (or `/loop` as a fallback — see below) — the mechanism that keeps re-invoking the
   session until the gate says stop.

## Starting a run

1. Confirm the queue reflects what you actually want done tonight — read
   `.handoff/AUTONOMOUS_QUEUE.md` end to end, including the `HALT` item, so there is no surprise
   about where it will stop.
2. Branch: `git checkout develop && git pull && git checkout -b feature/SPEC-NNN-slug`. The gate
   script refuses to run anywhere else.
3. **Pilot first, always** — the loop engineering guidance is explicit about this: pilot dynamic
   workflows before a large run. Launch with a low iteration/turn cap, watch it complete one real
   item cleanly (a real commit, a real gate pass), *then* relaunch for the full run. Do not go
   straight to an all-night cap on the first attempt.
4. Launch as a background agent so it survives the terminal closing:
   ```bash
   claude --bg --permission-mode dontAsk --model sonnet
   ```
   `--permission-mode dontAsk` matters specifically for unattended runs: the `ask` rules already in
   `.claude/settings.json` (`git push`, `git merge` outside this flow, `terraform apply`, `npm
   publish`) are **denied automatically** instead of waiting for someone who is not there. The loop
   cannot escalate its own privilege by nobody being around to answer a prompt.
5. Inside that session, start the goal loop:
   ```
   /goal scripts/autonomous_gate.py exits 0 - the application layer queue is empty and the full gate is green
   ```
   If `/goal` is unavailable in the installed version, fall back to `/loop` with no interval
   (self-paced): `/loop` and have it run `python scripts/autonomous_gate.py` each cycle, stopping
   itself when the exit code is 0 or 2. The queue, the gate script and the model policy do not
   change between the two — only the trigger mechanism does.
6. If the 5-hour usage window is a concern for an overnight run, enable `autoContinueAtUsageLimit`
   so the session waits for the window to reset and continues, rather than just stopping. This is
   separate from `/goal` — `/goal` decides *what* counts as done, this decides whether a usage pause
   ends the attempt.

## Watching it

- `claude agents` — list background agents and their status.
- `claude logs <id>` — see what it has actually done.
- `claude attach <id>` — reconnect interactively at any point.
- `git log --oneline feature/SPEC-NNN-slug` — the ground truth. Small, conventional commits, one
  per completed queue item, is what a healthy run looks like.

## Stopping it

- `claude attach <id>` then `/cancel-ralph` equivalent — for `/goal`, ending the session or
  pressing Esc during a `/loop` stops it. `claude agents stop <id>` from another terminal also
  works without attaching.
- If the gate halted it (exit 2): read the entry it appended to `.handoff/STATE.md` before doing
  anything else. That is the actual reason, not a guess.

## When it stops on its own

- **`exit 0` (done):** every queue item is ticked in `docs/specs/<spec>/tasks.md` and the gate is
  green. Run `verify-before-done` yourself before trusting it fully, then merge the feature branch
  into `develop` — self-service, per the branch policy, same as any other work.
- **`exit 2` on the `HALT` item:** the expected, good outcome for a queue that ends in one. Read
  `.handoff/STATE.md` for exactly what state everything before it is in, then pick up that item
  deliberately — Opus, plan mode, per `AGENTS.md`'s standing complexity rule.
- **`exit 2` for anything else** (wrong branch, scope violation, stuck on one item): something
  went wrong with the *setup*, not necessarily the work. Fix the cause, don't just relaunch the
  loop against the same state — `scripts/autonomous_gate.py` refuses to progress past a stuck item
  without a config or code change happening first.

## What this does not do

- Does not touch `main`, ever — the branch-policy hook enforces that at the tool-call level,
  identically for the loop as for an interactive session.
- Does not push anywhere. Publishing `develop` (or anything else) to a remote is still the user's
  call, made explicitly, not something a loop decides on its own.
- Does not install anything. If a queue item seems to need a new dependency, MCP or plugin, that
  is itself a signal to stop and ask, not to proceed — `docs/tooling/RESEARCH.md`'s "just in time,
  never speculative" rule applies here too.
- Does not run multiple specs in parallel. Specs in `docs/specs/ROADMAP.md` are dependency-ordered,
  not independent tracks — see the reasoning recorded in `.handoff/STATE.md` if this comes up again.
