## What and why

<!-- One paragraph. Link the spec. -->

Spec: `docs/specs/SPEC-NNN-slug/`

## Evidence

<!-- Paste real command output. A claim without output is not evidence. -->

```
ruff check .        ->
mypy .              ->
lint-imports        ->
pytest tests/unit   ->
```

## Eval impact

- [ ] No prompt / model / graph / retrieval / tool-contract change
- [ ] Changed and the eval suite was re-run: scores before -> after
- [ ] New eval cases added (which datasets?)

## Security checklist

- [ ] No secret added, printed or logged; new env vars are placeholders in `.env.example`
- [ ] External content stays fenced as untrusted data and cannot alter policy
- [ ] New/changed tools: schema, risk level, allowlist entry, full validation chain, audit row
- [ ] Authorization and `organization_id` isolation preserved
- [ ] No PII in logs, traces or fixtures; demo data is synthetic
- [ ] Audit trail still append-only
- [ ] New dependencies pinned and audited

## Architecture

- [ ] Layer boundaries respected (`lint-imports` green)
- [ ] Business logic in the domain, not in routers, tasks or graph nodes
- [ ] ADR written if this decision constrains future work

## Migrations

- [ ] None
- [ ] Backward-compatible, `upgrade` -> `downgrade` -> `upgrade` verified locally

## Notes for the reviewer

<!-- What you are unsure about. What you deliberately left out. -->
