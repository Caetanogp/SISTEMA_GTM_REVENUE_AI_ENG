# Playbook: spec-driven feature

The flow for any non-trivial change: **spec → plan → tasks → implement → verify**. No code before
`spec.md` is agreed with the user.

## 1. spec.md — what and why

Copy `docs/specs/TEMPLATE.md` into `docs/specs/SPEC-NNN-slug/spec.md` and fill in:

- **Problem** — the user/business problem, in the language of the project guide, not of the code.
- **User stories** — `As a <role>, I want <capability>, so that <outcome>`.
- **In scope / Out of scope** — the second list is the one that saves you. Be explicit about what
  this spec deliberately does not do.
- **Acceptance criteria** — numbered, each independently verifiable, phrased so that a test can
  assert it.
- **Risks** — security, data integrity, cost, latency. Which tools does this add, at what risk level?
- **Eval impact** — which datasets or scorers this touches, and what would count as a regression.

Ask the user to confirm before moving on. Ambiguity resolved here costs minutes; resolved during
implementation it costs a session.

## 2. plan.md — how

- Which layers are touched, and what goes in each (domain / application / infrastructure / apps).
- New ports and their signatures; new adapters and what they wrap.
- Data model changes and the migration strategy (backward-compatible, two-step).
- Trade-offs considered and rejected, with the reason. Future-you will ask.
- Test plan: what is unit, what is integration, what is adversarial.
- Eval plan: which cases get added.

Worth doing: have `staff-engineer-reviewer` review the plan before implementing. A second pass on a
plan is cheap; a second pass on 400 lines of code is not.

## 3. tasks.md — the working state

Ordered checklist, each item small enough to finish in one sitting and phrased so it is verifiable:

```markdown
- [ ] Add `RiskLevel` value object in `domain/risk.py` with unit tests for the boundaries
- [ ] Define `AccountRepository` port in `application/ports.py`
- [ ] Implement `SqlAlchemyAccountRepository` + integration test against the docker Postgres
```

This file is the source of the `Next` section in `.handoff/STATE.md`. Tick items as you finish them,
not in a batch at the end — the tick is what survives a session ending abruptly.

## 4. Implement

First, before any edit, land on the right branch:

```bash
git rev-parse --abbrev-ref HEAD          # main or develop? stop.
git checkout develop && git pull
git checkout -b feature/SPEC-NNN-slug
```

Then work inside out: domain → application → infrastructure → app. Tests alongside, not after.
Commit per logical step, conventional commits.

## 5. Verify and land

Run the `verify-before-done` playbook. Then update `tasks.md` and `.handoff/STATE.md`.

Once the gate is green, merge into `develop` yourself:

```bash
git checkout develop && git pull
git merge feature/SPEC-NNN-slug
git branch -d feature/SPEC-NNN-slug
```

`main` stays out of reach regardless — `develop` only reaches `main` through a release the user
performs. Once a GitHub remote exists, open a PR instead (same gate, more visibility and CI), but
the local merge is the default until then.

## Changing scope mid-flight

Edit `spec.md` first, then `plan.md`, then continue. A spec that no longer describes the code is
worse than no spec, because it is believed.
