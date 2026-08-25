---
description: Write the handoff state with evidence before ending the session
---

Follow the "Saving state" section of `docs/playbooks/handoff.md`.

Gather evidence before writing anything:

!`git log --oneline -5`
!`git status --short`

Then rewrite `.handoff/STATE.md` in full: frontmatter, Goal, Now, Done (every line with file:line,
commit SHA or command output), Next (3-5 concrete steps from tasks.md), Gotchas, Resume, Open
questions. Keep it under 100 lines.

Tick the matching items in the active `docs/specs/SPEC-NNN-*/tasks.md`, snapshot the file into
`.handoff/log/`, and commit with `chore(handoff): ...`.

Never write a Done entry you did not verify in this session.
