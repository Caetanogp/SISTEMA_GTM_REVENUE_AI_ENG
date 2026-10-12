# SPEC-011: Reply Intelligence Tasks

## Item 8 security closeout

The final verification checkbox also requires the approved security closeout:

- Replace the four ingestion B101 assertions with runtime invariant checks and focused regression
  coverage.
- Add a pinned `requirements-ci.txt` resolved from a clean Linux Python 3.12 environment; use it
  for Python CI installation and pip-audit without suppressing findings.
- Pass the existing CI Semgrep rulesets and all verification commands before closing Item 8.
- Keep the autonomous Item 8 scope synchronized with the approved files and record observed
  evidence in this task file and `.handoff/STATE.md`.

## Acceptance evidence

| Mapping | Observed file:line evidence |
|---|---|
| AC-01 authenticated reply registration and tenant scope | `apps/api/routes/replies.py:45`; `tests/unit/application/use_cases/test_reply.py:262` |
| AC-02 atomic reservation and idempotent replay | `packages/core/revops/application/use_cases/reply.py:126`; `tests/integration/test_reply_persistence.py:129` |
| AC-03 typed category, confidence, evidence, and action | `packages/core/revops/domain/values/reply.py:169`; `tests/unit/domain/values/test_reply.py:34` |
| AC-04 conservative opt-out precedence and no CRM mutation | `packages/core/revops/domain/values/reply.py:153`; `tests/unit/domain/values/test_reply.py:96` |
| AC-05 authorization, malformed output, injection, fake evidence, and PII handling | `tests/integration/test_reply_api.py:138`; `tests/adversarial/test_reply_intelligence_security.py:39` |
| AC-06 restart-safe checkpoint replay and direct terminal artifacts | `packages/core/revops/infrastructure/agent/reply_runtime.py:190`; `tests/integration/test_reply_api.py:221` |
| AC-07 immutable organization-scoped feedback history | `packages/core/revops/infrastructure/persistence/models.py:777`; `tests/unit/application/use_cases/test_reply.py:350` |
| AC-08 bilingual synthetic dataset and metric thresholds | `evals/datasets/reply_classification.jsonl:1`; `tests/unit/evals/test_reply_classification_scorer.py:38` |
| AC-09 strict low-risk tool and auditable version/usage records | `packages/core/revops/infrastructure/agent/tools.py:63`; `tests/unit/infrastructure/agent/test_reply_runtime.py:203` |
| AC-10 existing runtime compatibility | `tests/integration/test_agent_runs_api.py:1`; `tests/integration/test_reply_api.py:62` |
| AC-11 non-blocking same-connection checkpoint lock | `packages/core/revops/infrastructure/agent/reply_runtime.py:142`; `tests/integration/test_reply_runtime_lock.py:21` |
| AC-12 bounded, typed, canonical persisted artifact | `packages/core/revops/infrastructure/agent/reply_runtime.py:45`; `tests/unit/infrastructure/agent/test_reply_runtime.py:116` |
| AC-13 approved security closeout: runtime ingestion guards and pinned CI audit input | `packages/core/revops/application/use_cases/ingestion.py:116`; `tests/unit/application/use_cases/test_ingestion.py:325`; `.github/workflows/ci.yml:62`; `.github/workflows/ci.yml:72` |

- [x] Add reply domain values and deterministic classification policy for nine bilingual categories — verified by focused domain tests
- [x] Add reply DTOs, ports, use cases, and canonical tenant/contact validation — verified by application unit tests and mypy
- [x] Add additive replies, classification requests, and feedback persistence with atomic reservation/idempotency — verified by `pytest tests/integration/test_reply_persistence.py -q` (1 passed), Ruff, format check, mypy, and `git diff --check`
- [x] Add versioned prompt, low-risk tool, dedicated checkpointed reply graph, and bounded artifacts — verified by runtime unit/integration tests, prompt contract tests, and `python -m evals.gate`
- [x] Add authenticated reply/classification/result/feedback APIs without changing existing graph compositions — verified by `pytest tests/integration/test_reply_api.py tests/integration/test_agent_runs_api.py tests/integration/test_reply_persistence.py tests/integration/test_reply_runtime_lock.py -q` (8 passed), Ruff, format check, mypy, `lint-imports`, and `git diff --check`
- [x] Add the 90-case bilingual dataset and additive contract/baseline metric gates — verified by `python -m evals.gate` (contract 5/5; baseline 90/90, accuracy 1.00, macro-F1 1.00, unsubscribe recall 1.00)
- [x] Add adversarial, authorization, concurrency, restart, and regression coverage — verified by `pytest tests/adversarial -q` (32 passed) and `pytest tests/integration -q` (52 passed)
- [ ] Complete PDF traceability, security review, full verification, and handoff evidence — verified by the full gate and clean tree
