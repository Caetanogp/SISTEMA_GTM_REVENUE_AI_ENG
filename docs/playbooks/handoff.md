# Playbook: handoff

Read and write `.handoff/STATE.md` so the next agent — possibly a different model, with no memory of
this session — can be productive in one minute. Rules and format: `.handoff/PROTOCOL.md`.

## Loading state (start of session)

1. Read `.handoff/STATE.md`.
2. Verify it against reality, because a stale handoff is worse than none:
   ```bash
   git rev-parse --abbrev-ref HEAD    # must NOT be main or develop before you write code
   git status --short && git log --oneline -5
   cat docs/specs/<active-spec>/tasks.md
   ```
   If HEAD is on `main` or `develop`, create the feature branch before the first edit
   (`git checkout -b feature/SPEC-NNN-slug`). A hook blocks the commit otherwise, but finding out
   at commit time wastes the session.
3. If they disagree, trust the repository and correct `STATE.md` before starting.
4. Report back to the user in Portuguese, in four lines: active spec · what is in progress · the next
   three steps · anything blocked on them.
5. Do not start coding until you have done this.

## Saving state (end of session, or when a task changes state)

1. Gather evidence first — claims are not accepted:
   ```bash
   git log --oneline -5
   pytest tests/unit -q | tail -3
   ruff check . && mypy . && lint-imports
   ```
2. Rewrite `STATE.md` in full (do not append; it is a live document, not a log):
   - frontmatter: `agent`, `updated_at`, `branch`, `spec`, `phase`, `status`
   - **Goal** — one sentence, the active spec objective
   - **Now** — what is genuinely in flight; empty if you finished cleanly
   - **Done** — newest first, every line with file:line, commit SHA, or command output
   - **Next** — 3 to 5 concrete ordered steps, taken from `tasks.md`
   - **Gotchas** — traps found, approaches rejected and why
   - **Resume** — the literal commands to get productive again
   - **Open questions** — what needs the user
3. Tick the matching boxes in `docs/specs/<spec>/tasks.md`.
4. Keep it under 100 lines. Archive finished specs out of `Done`.
5. When switching agents, snapshot it:
   ```bash
   cp .handoff/STATE.md ".handoff/log/$(date +%Y-%m-%d-%H%M)-claude.md"   # or -codex
   ```
6. Commit: `chore(handoff): update state after <what happened>`.

## What makes a handoff fail

- `Done` entries without evidence — the next agent re-does the work, or worse, trusts it.
- `Next` steps that are goals, not actions ("improve test coverage" vs "add unit tests for
  `RiskClassifier.classify` covering the medium/high boundary").
- A `Resume` block that assumes context the next session does not have.
- Forgetting to update it at all. This is the only failure mode that costs a whole session.
