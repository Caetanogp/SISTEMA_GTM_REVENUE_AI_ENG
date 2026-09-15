# SPEC-006 tasks

- [x] Reconcile the roadmap, handoff and source references for SPEC-005 merge and SPEC-006 start - verified by documentation checks.
- [x] Define application gateway configuration, health and sanitized failure contracts - verified by unit tests and `lint-imports`.
- [x] Add strict live settings, provider route validation and versioned Decimal pricing catalog - verified by configuration and pricing tests.
- [x] Implement the OpenAI Responses adapter over HTTPX with strict JSON Schema and usage parsing - verified by MockTransport tests.
- [x] Implement the Anthropic Messages adapter over HTTPX with strict JSON Schema and usage parsing - verified by MockTransport tests.
- [x] Implement bounded retry, backoff, fallback classification and passive health state - verified by deterministic route tests.
- [x] Integrate gateway construction and lifecycle cleanup into the API composition root - verified by API tests with disabled and injected gateways.
- [x] Add the sanitized `GET /health/llm` endpoint - verified by response and secret-redaction tests.
- [x] Version the prioritization prompt for English and Portuguese output - verified by prompt and eval tests.
- [x] Add explicit `agent_runs.thread_id` with backward-compatible migration and journal durability - verified by migration and integration tests.
- [x] Record actual provider, model, latency, token, cost, fallback and sanitized failure metadata - verified by terminal event assertions.
- [x] Add mandatory offline gateway contract evals and optional live smoke documentation - verified by `python -m evals.run --suite all` and the new contract suite.
- [x] Update PDF traceability, ADRs, security documentation and handoff with file:line evidence - verified by repository documentation checks.
- [x] Run the complete `verify-before-done` checklist and autonomous gate - `python scripts/autonomous_gate.py` reported `GOAL ACHIEVED: all queue items done, full gate green`.
