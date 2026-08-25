---
description: Load the current development state and report where we stopped
---

Read `.handoff/STATE.md`, then verify it against reality:

!`git status --short`
!`git log --oneline -5`

Follow the "Loading state" section of `docs/playbooks/handoff.md`.

If the file disagrees with the repository, trust the repository and correct the file before doing
anything else. Then report to the user in Portuguese, in four lines: active spec, what is in
progress, the next three steps, and anything blocked on them.
