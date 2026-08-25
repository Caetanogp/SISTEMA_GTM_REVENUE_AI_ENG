# Handoff protocol

Development on this repo alternates between **Claude Code** and **Codex** as usage limits run out.
The next session may be a different model with no memory of this one. `.handoff/STATE.md` is the
bridge.

## The contract

1. **Read `STATE.md` first.** Before touching code, restate to the user: the active spec, what is in
   progress, and the next three steps. If `STATE.md` disagrees with the repo, trust the repo (`git
   log`, `git status`, the test run) and fix `STATE.md`.
2. **Write `STATE.md` last.** Before the session ends — or the moment a task changes state — update
   it. A session that ends without updating it has failed the handoff, whatever else it delivered.
3. **When switching agents**, copy the current `STATE.md` to
   `.handoff/log/YYYY-MM-DD-HHMM-<agent>.md`. The log is append-only history; `STATE.md` is the
   single live document.
4. **`STATE.md` is committed.** State travels with the repository, not with a machine.

## Evidence rule

The `Done` section only accepts verified facts. Every entry carries evidence:

- bad: `fixed the scoring bug`
- good: `fixed the scoring bug — packages/core/revops/domain/scoring.py:88, commit a1b2c3d, pytest tests/unit/test_scoring.py 11/11`

Valid evidence is a file:line, a commit SHA, or the output of a command you actually ran. If you did
not observe it, it does not go in `Done`. Work that is written but unverified goes in `Now`, marked
as unverified.

## Section meanings

| Section | Contains | Trap to avoid |
|---|---|---|
| frontmatter | agent, updated_at, branch, spec, phase, status | leaving `updated_at` stale |
| Goal | the active spec objective, one sentence | restating the whole product vision |
| Now | what is in flight right now: files open, half-done edits, failing test | listing finished work |
| Done | verified work **for this spec**, newest first, with evidence | claims without evidence |
| Next | 3–5 concrete ordered steps, straight from `tasks.md` | vague items like "improve tests" |
| Gotchas | traps found, rejected approaches, and why | repeating what is already in the docs |
| Resume | the literal commands to get productive again | assuming the next agent knows the setup |
| Open questions | what is blocked on the user | questions you could answer yourself |

## Keep it small

`STATE.md` is read at the start of every session, by both agents. Target under 100 lines. Finished
specs are archived into `.handoff/log/` and dropped from `Done` — history lives in git and in the
spec folder, not here.

## Entry points

| Agent | Load state | Save state |
|---|---|---|
| Claude Code | `/handoff-in` | `/handoff-out` |
| Codex | `.codex/prompts/handoff-in.md` | `.codex/prompts/handoff-out.md` |

Both run the same procedure: `docs/playbooks/handoff.md`.
