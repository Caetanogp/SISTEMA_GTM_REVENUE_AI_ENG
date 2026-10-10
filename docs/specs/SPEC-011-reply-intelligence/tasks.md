# SPEC-011: Reply Intelligence Tasks

- [ ] Add reply domain values and deterministic classification policy for nine bilingual categories — verified by focused domain tests
- [ ] Add reply DTOs, ports, use cases, and canonical tenant/contact validation — verified by application unit tests and mypy
- [ ] Add additive replies, classification requests, and feedback persistence with atomic reservation/idempotency — verified by migration and PostgreSQL integration tests
- [ ] Add versioned prompt, low-risk tool, dedicated checkpointed reply graph, and bounded artifacts — verified by runtime unit tests and prompt contract tests
- [ ] Add authenticated reply/classification/result/feedback APIs without changing existing graph compositions — verified by API integration tests
- [ ] Add the 90-case bilingual dataset and additive contract/baseline metric gates — verified by `python -m evals.gate`
- [ ] Add adversarial, authorization, concurrency, restart, and regression coverage — verified by adversarial and integration suites
- [ ] Complete PDF traceability, security review, full verification, and handoff evidence — verified by the full gate and clean tree
