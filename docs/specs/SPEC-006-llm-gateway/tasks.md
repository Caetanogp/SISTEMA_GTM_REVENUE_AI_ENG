# SPEC-006 tasks

- [ ] Reconcile the roadmap, handoff and source references for SPEC-005 merge and SPEC-006 start - verified by documentation checks.
- [ ] Define application gateway configuration, health and sanitized failure contracts - verified by unit tests and `lint-imports`.
- [ ] Add strict live settings, provider route validation and versioned Decimal pricing catalog - verified by configuration and pricing tests.
- [ ] Implement the OpenAI Responses adapter over HTTPX with strict JSON Schema and usage parsing - verified by MockTransport tests.
- [ ] Implement the Anthropic Messages adapter over HTTPX with strict JSON Schema and usage parsing - verified by MockTransport tests.
- [ ] Implement bounded retry, backoff, fallback classification and passive health state - verified by deterministic route tests.
- [ ] Integrate gateway construction and lifecycle cleanup into the API composition root - verified by API tests with disabled and injected gateways.
- [ ] Add the sanitized `GET /health/llm` endpoint - verified by response and secret-redaction tests.
- [ ] Version the prioritization prompt for English and Portuguese output - verified by prompt and eval tests.
- [ ] Add explicit `agent_runs.thread_id` with backward-compatible migration and journal durability - verified by migration and integration tests.
- [ ] Record actual provider, model, latency, token, cost, fallback and sanitized failure metadata - verified by terminal event assertions.
- [ ] Add mandatory offline gateway contract evals and optional live smoke documentation - verified by `python -m evals.run --suite all` and the new contract suite.
- [ ] Update PDF traceability, ADRs, security documentation and handoff with file:line evidence - verified by repository documentation checks.
- [ ] Run the complete `verify-before-done` checklist and autonomous gate - verified by passing command output and commit SHA.
