# SPEC-011 Reply Intelligence Security Review

Reviewed: 2026-10-12

## Scope

The review covers the authenticated reply API, untrusted reply prompt boundary, low-risk
classification tool, checkpointed runtime, tenant-scoped persistence, feedback history, and
synthetic evaluation data introduced by SPEC-011.

## Findings

No new security finding was identified in the reviewed scope.

| Control | Evidence |
|---|---|
| Untrusted reply text is fenced as data and injection/PII cases are covered | `packages/core/revops/infrastructure/agent/prompt_loader.py:73`; `tests/adversarial/test_reply_intelligence_security.py:39` |
| The classification tool is explicitly low risk and analysis-only | `packages/core/revops/infrastructure/agent/tools.py:63`; `packages/core/revops/infrastructure/agent/reply_runtime.py:225` |
| Tenant identity is authenticated rather than accepted from request data | `apps/api/routes/replies.py:45`; `tests/integration/test_reply_api.py:138` |
| Reply classification and feedback are idempotent and append-only | `packages/core/revops/application/use_cases/reply.py:126`; `packages/core/revops/infrastructure/persistence/models.py:777` |
| Raw reply text is excluded from terminal journal metadata | `tests/unit/application/use_cases/test_reply.py:313`; `tests/unit/infrastructure/agent/test_reply_runtime.py:203` |
| Synthetic bilingual data and fake-evidence rejection are covered | `evals/datasets/reply_classification.jsonl:1`; `tests/adversarial/test_reply_intelligence_security.py:54` |

## Automated evidence

Observed feature verification on 2026-10-11: `pytest tests/adversarial -q` passed (32 tests),
`python -m evals.run --suite all` passed (including reply classification 90/90), and
`python scripts/check_pdf_traceability.py` passed (86 rows, pages 1-20). Gitleaks previously
reported no leaks; its recorded run had a restricted `.pytest_cache` access warning.

Security-tool rerun on 2026-10-12:

- `semgrep --version` is unavailable on `PATH`; the CI workflow runs Semgrep with the configured
  `p/default`, `p/python`, and `p/secrets` rulesets.
- Before the remediation, `bandit -r packages apps -q` reported four low-severity B101 findings in
  `packages/core/revops/application/use_cases/ingestion.py`. Commit `dc9e210` replaces those
  assertions with explicit invariant checks; the same Bandit command now exits 0 with no findings.
- `pytest tests/unit/application/use_cases/test_ingestion.py -q` passed (10 tests), and the same
  test file passed under `python -O -m pytest ... -q` (10 tests). Ruff, format check, and targeted
  mypy also passed for the changed use case and test.
- `requirements-ci.txt` pins 139 distributions resolved for CPython 3.12 on Linux x86_64. It was
  generated with pip's cross-target wheel resolution, not from the stale Windows editable install;
  see the official [pip download target options](https://pip.pypa.io/en/stable/cli/pip_download/).
- `pip-audit --strict --no-deps -r requirements-ci.txt` passed on 2026-10-12 with no known
  vulnerabilities reported for that pinned inventory. This does not guarantee future advisories
  will not affect it.
- CI now installs the exact pins without dependency re-resolution, installs the local project
  without resolving dependencies, and runs `pip check`. Eval CI also triggers when the lock or
  `pyproject.toml` changes. These Linux CI installation steps have not yet run on GitHub.
- The configured Semgrep rulesets (`p/default`, `p/python`, and `p/secrets`) have not yet produced
  an observed CI result. Local `semgrep` is unavailable.

Full security closeout remains open pending observed GitHub CI evidence for the complete test
matrix and Semgrep. The manually dispatched Eval gate passed the locked Linux installation, PDF
traceability, evals, and thresholds. No dependency, credential, MCP server, external write, or
security relaxation was introduced by SPEC-011.

## Closeout verification

Observed on 2026-10-12: `ruff check .`, `ruff format --check .`, `mypy .` (201 source files),
`pytest tests/unit tests/architecture -q` (508 passed), `pytest tests/adversarial -q` (32 passed),
`python -m evals.gate` (all 11 suites passed), `python scripts/check_pdf_traceability.py` (86 rows,
pages 1-20), `python scripts/check_agent_docs.py`, `bandit -r packages apps -q`, `lint-imports`,
`gitleaks detect --no-git`, and `git diff --check` passed. The full integration suite had 51 passes
and one unrelated failure in `test_attribution_migration_round_trip`: duplicate local
`knowledge_processing_events` keys prevent a historical downgrade from recreating a unique
constraint. No migration or database data was altered to work around it. Item 8 remains open until
the required GitHub Semgrep and locked Linux CI jobs pass, and the integration baseline passes in
its intended clean CI database.
