# SPEC-011 Reply Intelligence Security Review

Reviewed: 2026-10-11

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

Observed closeout results on 2026-10-11: `pytest tests/adversarial -q` passed (32 tests),
`python -m evals.run --suite all` passed (including reply classification 90/90), and
`python scripts/check_pdf_traceability.py` passed (86 rows, pages 1-20). `gitleaks detect
--no-git` reported no leaks but exited unsuccessfully because the sandbox denied access to
`.pytest_cache`; `semgrep` was unavailable on `PATH`; `bandit -r packages apps -q` reported four
pre-existing low-severity B101 findings in `packages/core/revops/application/use_cases/ingestion.py`;
and `pip-audit` could not reach PyPI because sandbox networking is denied. Full closeout therefore
remains open. No dependency, credential, MCP server, external write, or security relaxation was
introduced by SPEC-011.
