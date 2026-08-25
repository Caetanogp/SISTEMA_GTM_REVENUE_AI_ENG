# Playbook: verify before done

Run this before saying anything is finished. "It should work" is not a result; a command output is.

## The gate

```bash
ruff check . && ruff format --check .
mypy .
lint-imports
pytest tests/unit -q
pytest tests/integration -q      # if adapters, API or DB were touched
pytest tests/adversarial -q      # if prompts, tools or context assembly were touched
python -m evals.run --suite all  # if prompts, model config or the graph changed
python scripts/check_agent_docs.py
gitleaks detect --no-git
```

## Then check the things a command cannot

- **Acceptance criteria** — reread `spec.md` and confirm each numbered criterion is actually met.
  Not "the code exists" — the criterion.
- **The failure paths** — what happens on invalid input, a provider timeout, a rejected approval, a
  duplicate request? If you have not seen the error path run, you have tested half the feature.
- **Security** — new secret? new external content in context? new tool or scope? new PII in a log?
  If yes to any, run the `security-review` playbook.
- **Boundaries** — did anything framework-shaped end up in `domain/` or `application/`?
  `lint-imports` catches imports, not a domain rule quietly moved into a router.
- **Evidence** — collect the file:line and the command output you will put in `.handoff/STATE.md`.

## Reporting honestly

- Say what passed, what failed, and what you did not run. A skipped integration suite is reported as
  skipped, not silently omitted.
- Never present code you have not executed as working.
- If a test fails and you cannot fix it, stop and report it. Do not delete the test, mark it
  `xfail`, or loosen the assertion to get green.

## Last step

Update `docs/specs/<spec>/tasks.md` and `.handoff/STATE.md` with the evidence, then commit.
