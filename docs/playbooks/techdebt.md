# Playbook: tech debt sweep

Run at the end of a working session, before the handoff. Cheap when done often, expensive when not.

## Sweep

```bash
git diff develop --stat                  # what this branch actually changed
ruff check . --select=ALL --statistics   # what the strict ruleset would say
mypy . | tail -20
lint-imports
```

Then look for:

- **Duplication** — the same logic in two places, or a helper that already exists in
  `application/` being reimplemented in a router or a node.
- **Layer drift** — a business rule that quietly settled in an adapter or a router. `lint-imports`
  sees imports, not misplaced logic.
- **Dead code** — unused ports, adapters with no caller, prompts no graph references, feature flags
  that will never be false again.
- **Silent failure** — `except Exception: pass`, a swallowed retry, an error path with no log and no
  audit row.
- **Test gaps** — new branches with no test, and tests that assert nothing meaningful.
- **Stale docs** — an ADR contradicted by the code, a spec whose acceptance criteria drifted, a
  playbook describing a command that no longer exists.

## Rules

- Fix what is small and safe now, in a separate `chore:` commit. Do not mix cleanup into a feature
  commit — it makes the diff unreviewable.
- Anything larger becomes an item in `tasks.md` or a new spec, not a silent TODO.
- Never "clean up" code the current spec does not touch. Scope creep at the end of a session is how
  a green branch turns red.
- If a correction came from the user this session, update `AGENTS.md` or the relevant playbook so
  the mistake cannot repeat. That update is the highest-value line of the whole sweep.
