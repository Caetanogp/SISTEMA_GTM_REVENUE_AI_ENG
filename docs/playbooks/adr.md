# Playbook: architecture decision record

Write an ADR when a decision constrains future work: a framework, a boundary, a data model shape, a
security posture, a trade-off someone will later want to reverse.

Do not write one for a naming choice or a refactor with no consequence.

## Format

`docs/decisions/ADR-NNNN-slug.md`:

```markdown
# ADR-NNNN: <decision in one line>

- **Status:** proposed | accepted | superseded by ADR-NNNN
- **Date:** YYYY-MM-DD
- **Context spec:** SPEC-NNN (if any)

## Context
What forced a decision. Constraints, requirements, what was already true.

## Options considered
1. **<option>** — pros / cons
2. **<option>** — pros / cons

## Decision
What was chosen, stated plainly.

## Consequences
What becomes easy. What becomes hard. What we accept as the cost.
What would make us revisit this.
```

## Rules

- Record the options that were rejected, and why. An ADR that only states the winner teaches nothing
  and gets re-litigated in six months.
- Be honest about the cost. Every real decision has one; an ADR with no downside is marketing.
- Never edit an accepted ADR to change the decision. Write a new one and mark the old superseded —
  the history is the value.
- Link it from the spec that triggered it.
