# SPEC-011: Reply Intelligence Tasks

- [x] Add reply domain values and deterministic classification policy for nine bilingual categories — verified by focused domain tests
- [x] Add reply DTOs, ports, use cases, and canonical tenant/contact validation — verified by application unit tests and mypy
- [x] Add additive replies, classification requests, and feedback persistence with atomic reservation/idempotency — verified by `pytest tests/integration/test_reply_persistence.py -q` (1 passed), Ruff, format check, mypy, and `git diff --check`
- [x] Add versioned prompt, low-risk tool, dedicated checkpointed reply graph, and bounded artifacts — verified by runtime unit/integration tests, prompt contract tests, and `python -m evals.gate`
- [x] Add authenticated reply/classification/result/feedback APIs without changing existing graph compositions — verified by `pytest tests/integration/test_reply_api.py tests/integration/test_agent_runs_api.py tests/integration/test_reply_persistence.py tests/integration/test_reply_runtime_lock.py -q` (8 passed), Ruff, format check, mypy, `lint-imports`, and `git diff --check`
- [x] Add the 90-case bilingual dataset and additive contract/baseline metric gates — verified by `python -m evals.gate` (contract 5/5; baseline 90/90, accuracy 1.00, macro-F1 1.00, unsubscribe recall 1.00)
- [ ] Add adversarial, authorization, concurrency, restart, and regression coverage — verified by adversarial and integration suites
- [ ] Complete PDF traceability, security review, full verification, and handoff evidence — verified by the full gate and clean tree
