---
description: Scaffold a new spec folder (spec.md, plan.md, tasks.md)
argument-hint: <slug>
---

Create a new spec for: $ARGUMENTS

Existing specs (use the next free number):

!`ls docs/specs`

Follow `docs/playbooks/spec-feature.md`. Copy `docs/specs/TEMPLATE.md` into
`docs/specs/SPEC-NNN-$ARGUMENTS/spec.md` and fill it in with the user, asking about anything
ambiguous rather than assuming. Write `plan.md` only after the spec is agreed, and `tasks.md` only
after the plan is agreed.
