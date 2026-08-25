---
description: End-of-session sweep for duplication, layer drift and dead code
---

Follow `docs/playbooks/techdebt.md`.

!`git diff develop --stat`

Fix what is small and safe in a separate `chore:` commit. Turn anything larger into an item in the
active `tasks.md` or a new spec. Do not clean up code outside the scope of the current spec.

If the user corrected you this session, update `AGENTS.md` or the relevant playbook so it cannot
happen again.
