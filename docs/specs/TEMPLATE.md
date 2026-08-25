# SPEC-NNN: <title>

- **Status:** draft | agreed | in progress | done
- **Owner:** <who>
- **Roadmap phase:** <0-6, from the project guide>
- **Created:** YYYY-MM-DD

## Problem

What is broken or missing, in business terms. Why it matters now. Who feels it.

## User stories

- As a `<role>`, I want `<capability>`, so that `<outcome>`.

## In scope

- ...

## Out of scope

Be explicit. This list is what prevents the spec from quietly growing during implementation.

- ...

## Acceptance criteria

Numbered, independently verifiable, phrased so a test can assert them.

1. Given `<state>`, when `<action>`, then `<observable result>`.
2. ...

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| | read / write / external | low / medium / high | yes / no |

## Data model impact

New entities, new fields, migrations, indexes. Backward-compatible plan.

## Security considerations

New external content in context? New scopes or credentials? New PII? What adversarial case does
this add to `tests/adversarial/`?

## Eval impact

Which datasets and scorers this touches. What counts as a regression. Which new cases get added.

## Risks and open questions

- ...

---

# plan.md (separate file)

Layers touched · new ports and signatures · adapters · migration strategy · trade-offs considered
and rejected, with reasons · test plan (unit / integration / adversarial) · eval plan · rollout.

# tasks.md (separate file)

Ordered checklist, each item finishable in one sitting and verifiable:

```markdown
- [ ] <verb> <what> in `<path>` — verified by `<command or assertion>`
```
