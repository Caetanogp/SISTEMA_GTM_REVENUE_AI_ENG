# SPEC-004 tasks: core agent tool runtime

## Specification and contracts

- [ ] Review and approve `spec.md` scope, acceptance criteria, risks, and out-of-scope boundaries.
- [ ] Review and approve `plan.md` layer contracts, migration strategy, trade-offs, and eval plan.
- [ ] Define the final tool-result event shape and compatibility behavior in an ADR or existing
  decision record before implementation.

## Domain and application

- [ ] Register `get_pipeline_metrics` and `prepare_followup` in the deny-by-default risk policy, with
  unit coverage for all five tools and HITL behavior.
- [ ] Add strict argument/result DTOs and common `completed`/`clarification`/`unsupported` outcomes
  with unit tests for unknown fields, bounds, and invalid identifiers.
- [ ] Define the tool catalog and single-tool executor ports in the application layer, with tests
  proving that model-provided organization or actor identity is ignored.
- [ ] Implement application use cases for account search, canonical account context, pipeline stage
  snapshot, email draft preparation, and the existing task proposal flow.

## Infrastructure and graph

- [ ] Implement tenant-scoped SQLAlchemy adapters for search, canonical context, and pipeline
  snapshot, with query-level limits and repository tests.
- [ ] Implement the configurable OpenAI Responses adapter with structured output, `store=false`,
  timeout/retry bounds, usage metadata, and fake-gateway tests without network access.
- [ ] Add versioned English/Portuguese routing and tool prompts and persist prompt/model configuration
  metadata for reproducibility.
- [ ] Adapt the graph runner to select and execute at most one tool per run, preserving checkpoint,
  audit, canonical resolution, and create-task HITL behavior.
- [ ] Extend API response and SSE schemas additively for typed results and structured clarification/
  unsupported outcomes; cover tenant authorization and approval/resume integration flows.

## Verification and closeout

- [ ] Add offline eval cases and scorer coverage for all five tools, both languages, safety negatives,
  argument boundaries, and no-side-effect outcomes.
- [ ] Add adversarial tests for prompt injection, cross-tenant access, unknown tools, malformed output,
  over-limit requests, and unapproved writes.
- [ ] Run `ruff check .`, `ruff format --check .`, `mypy .`, `lint-imports`, unit, integration,
  adversarial, offline eval, documentation, and secret scans; record observed evidence.
- [ ] Update `.handoff/STATE.md` with file:line evidence and the final verification output before
  merge; regenerate the autonomous queue only after all scope and verification tasks are complete.
