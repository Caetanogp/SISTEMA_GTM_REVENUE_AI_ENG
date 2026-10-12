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
- `bandit -r packages apps -q` exits 1 with four low-severity B101 findings at lines 115-116 and
  389-390 of `packages/core/revops/application/use_cases/ingestion.py`.
- `pip-audit --strict` does not reach a vulnerability report: dependency collection fails because
  the globally installed editable `agentic-revops-platform` distribution is not published on
  PyPI. `pip show` reports that editable install points to the OneDrive checkout, not the
  authoritative `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG` checkout. `--skip-editable` also fails while
  collecting that editable distribution.
- No Python lockfile is present in the repository root, although `pyproject.toml` describes a
  lockfile as the source of exact dependency versions. CI installs from lower-bound requirements
  with `pip install -e ".[dev]"`.

Full security closeout remains open. No dependency, credential, MCP server, external write, or
security relaxation was introduced by SPEC-011. The dependency set must be audited from a clean,
reproducible environment before its risk can be characterized; the existing Bandit findings are
outside SPEC-011's reply-specific behavior and require a separately authorized scope change or a
documented security waiver.
