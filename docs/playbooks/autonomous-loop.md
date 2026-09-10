# Playbook: autonomous loop ("night shift")

How to run unattended development work on a pre-approved queue while the user is away from the
computer. Grounded in Anthropic's loop engineering taxonomy
([claude.com/blog/getting-started-with-loops](https://claude.com/blog/getting-started-with-loops)):
our case is **goal-based** — a task with a verifiable exit criterion, evaluated by a separate
process rather than the model's own say-so.

## The three pieces

1. **`.handoff/AUTONOMOUS_QUEUE.md`** — the only source of work. Ordered items, each with a
   declared file scope and a verifiable done criterion. An executor that discovers an unresolved
   technical design returns `architecture_required` before implementation. Product, security,
   dependency, destructive migration, external action, or non-dominant choices return
   `HUMAN_REQUIRED` and stop.
2. **`scripts/autonomous_gate.py`** — the referee. Never trust the model's own "I'm done" — this
   script decides, deterministically: `exit 0` (goal achieved), `exit 1` (keep going), `exit 2`
   (HALT — wrong branch, scope violation, the next item needs a human, or too many consecutive
   failures on the same item). On `exit 2` it writes the reason to `.handoff/STATE.md` itself.
3. **A supervisor** — Codex uses `scripts/codex_loop_supervisor.py`, which invokes one executor turn
   at a time and can escalate bounded technical design. Claude uses `/goal` (or `/loop`) and retains
   its hard Plan Mode stop because it has no equivalent external supervisor in this repository.

## Codex architecture escalation

The normal Codex executor uses the configured economical model at `medium` reasoning. When it
returns `architecture_required`, the supervisor requires a clean worktree and then invokes:

1. a read-only `gpt-5.6-sol` architect at `xhigh` reasoning;
2. a separate read-only `gpt-5.6-sol` reviewer at `xhigh` reasoning;
3. a deterministic policy check over the plan and exact requested paths.

The reviewer may request one revision, for at most two architect-review attempts in total. An
approved plan is hashed, recorded in the handoff, and passed back to the economical executor. A
scope overlay is stored outside the checkout and bound to branch, queue item and baseline; only the
external supervisor passes it to the gate. The executor cannot edit or mint that authorization.
The supervisor also hashes its queue, policy, prompt, launcher, and referee before the first child
turn and verifies those hashes before processing any child outcome or running the gate.

The escalation may resolve reversible implementation architecture already required by an approved
spec. It may not change product scope or invent a public contract, add a dependency, authorize a
destructive migration, weaken security or verification, require an external action, or choose when
there is no dominant safe recommendation. Those conditions are always `HUMAN_REQUIRED`. The
trade-off and rejected alternatives are recorded in
`docs/decisions/ADR-0007-bounded-autonomous-architecture-escalation.md`.

## Upgrading the supervisor during an active item

A committed supervisor upgrade is intentionally outside an implementation item's scope. Do not
delete the ignored gate-state file or silently move its baseline. Create a one-time JSON approval
outside the checkout, bound to the current branch, previous baseline SHA, exact target SHA, current
done count, and the sorted exact `git diff --name-only <previous>..HEAD` path list. Its contract is:

```json
{
  "version": 1,
  "action": "rollover-supervisor-baseline",
  "branch": "feature/SPEC-NNN-slug",
  "previous_baseline_sha": "<40 hex characters>",
  "target_sha": "<40 hex characters>",
  "baseline_done_count": 0,
  "changed_paths": ["scripts/autonomous_gate.py"]
}
```

With a clean worktree, apply it once:

```powershell
python scripts/autonomous_gate.py --baseline-rollover-authorization "$env:TEMP\rollover.json"
```

The gate verifies the external location, ancestry, branch, done count, exact diff, and a restricted
supervisor-upgrade path allowlist before updating its ignored state. A stale or reused approval
fails closed. Run the ordinary gate again after the rollover and retain the observed command as
handoff evidence.

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
4. **Launch in the main checkout — never a worktree for this project.** This reverses earlier
   guidance in this file; both reasons
   are hard, reproduced findings, not preferences:
   - `--bg` sessions default to `worktree.bgIsolation: "worktree"` and refuse Write/Edit until
     `EnterWorktree` is called. But `revops` resolves through a PEP 660 editable install pinned to
     **absolute paths baked in at `pip install -e ".[dev]"` time**, in a global per-user
     site-packages, not a project `.venv`. A git worktree is a separate directory tree —
     `import revops...` inside it silently keeps resolving to the **main checkout's** files
     regardless of `cwd`. Every test, and the gate's own `pytest` run, exercises stale code
     forever. Reproduced and root-caused live: SPEC-001 persistence, 2026-08-29
     (`.handoff/log/2026-08-29-*-claude.md`) — a full Item was drafted and "verified" inside a
     worktree, then found to have never actually run against the new code at all.
   - `--bg` sessions also never get the native "wait for a usage limit to reset, then continue"
     behavior — confirmed against `code.claude.com/docs/en/interactive-mode`: *"Claude Code doesn't
     offer the wait at all in these cases: Background sessions and `-p` runs."* A `--bg` session
     that hits the 5-hour window simply stops, unattended, with nothing to resume it. Reproduced:
     SPEC-001 application layer, pilot 3, 2026-08-27.
   For a Codex run, launch the external supervisor in a terminal left open:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/start_codex_loop.ps1 -MaxTurns 100
   ```
   The launcher defaults resolved implementation to `gpt-5.6-terra/medium` and architecture plus
   review to `gpt-5.6-sol/xhigh`. Override those parameters only for a measured model-policy change.

   For a Claude run, both problems point to a foreground interactive session. Launch with:
   ```bash
   claude --permission-mode dontAsk --model sonnet
   ```
   in a real terminal window, left open (not a background job). `--permission-mode dontAsk`
   matters specifically for unattended runs: the `ask` rules already in `.claude/settings.json`
   (`git push`, `git merge` outside this flow, `terraform apply`, `npm publish`) are **denied
   automatically** instead of waiting for someone who is not there. The loop cannot escalate its
   own privilege by nobody being around to answer a prompt.
   For the machine to actually survive the night: disable sleep and the lid-close action (Windows:
   Settings > System > Power & battery > set both "sleep" rows and both "lid close" rows to
   Never/Do nothing) — the OS suspending is indistinguishable from the process dying.
5. Inside a Claude session, start the goal loop:
   ```
   /goal scripts/autonomous_gate.py exits 0 - the queue is empty and the full gate is green
   ```
   If `/goal` is unavailable in the installed version, fall back to `/loop` with no interval
   (self-paced): `/loop` and have it run `python scripts/autonomous_gate.py` each cycle, stopping
   itself when the exit code is 0 or 2. The queue, the gate script and the model policy do not
   change between the two — only the trigger mechanism does.
6. `autoContinueAtUsageLimit` (default `true` in a claude.ai-subscription interactive session —
   confirm with `/config`) is what lets the session survive the 5-hour usage window: it waits and
   resumes on its own once the window resets, no worktree involved. It re-arms itself for up to two
   consecutive hits before giving up and asking a human — expect at most that many unattended
   resumes in one night.

## Watching it

- Codex: inspect the foreground supervisor output, `git log --oneline`, and the temporary artifact
  directory printed at startup. A healthy escalation shows executor -> architect -> reviewer ->
  executor without an intervening implementation diff.
- `claude agents` — list running sessions and their status (interactive sessions show
  `busy`/`idle`/`waiting`, not the `background`-job states `--bg` would show).
- `git log --oneline feature/SPEC-NNN-slug` — the ground truth, straight on the branch from step 2
  since this runs in the main checkout, no worktree to look under. Small, conventional commits, one
  per completed queue item, is what a healthy run looks like.
- `SendMessage` (from another session on this machine) can nudge it after a live fix — see
  `.handoff/log/2026-08-28-*-claude.md` for the cross-session-messaging mechanics and the
  `crossSessionInbound` caveat (a message the receiving session doesn't auto-accept just sits held;
  the fix landing in a commit is often enough on its own, the session re-checks the gate later).

## Stopping it

- Codex: press Ctrl+C in the supervisor terminal. Do not kill only a child `codex exec` and leave
  the supervisor running.
- `claude attach <id>` then `/cancel-ralph` equivalent — for `/goal`, ending the session or
  pressing Esc during a `/loop` stops it. `claude agents stop <id>` from another terminal also
  works without attaching.
- If the supervisor or gate halted (exit 2): read the entry appended to `.handoff/STATE.md` before doing
  anything else. That is the actual reason, not a guess.

## When it stops on its own

- **`exit 0` (done):** every queue item is ticked in `docs/specs/<spec>/tasks.md` and the gate is
  green. Run `verify-before-done` yourself before trusting it fully, then merge the feature branch
  into `develop` — self-service, per the branch policy, same as any other work.
- **Codex `architecture_required`:** this is not a process exit. The supervisor automatically runs
  its read-only architect/reviewer flow and resumes only after approval.
- **`exit 2` / `HUMAN_REQUIRED`:** read `.handoff/STATE.md` for the exact reason. Do not relaunch
  against the same state; resolve it deliberately with the user.
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
