---
agent: codex
updated_at: 2026-10-07
branch: develop
spec: SPEC-009-single-agent-tool-runtime
phase: "SPEC-009 bounded runtime implemented, fully verified, and merged into develop"
status: merged_into_develop
---

# Current state

## Goal

Implement the PDF-aligned bounded single-agent tool runtime described by SPEC-009.

## Now

SPEC-008 is closed and fully verified. SPEC-009 has a bounded dispatcher, three typed tool
adapters, checkpoint/HITL reuse, sanitized lifecycle evidence, offline contract evals, adversarial
coverage, and API integration coverage. Full repository verification and the gate are green. The
verified feature branch was merged into `develop` as `9ec47e3`. No SPEC-009 autonomous queue or
loop is running; the checked-in autonomous queue remains the historical SPEC-008 queue and is not
active.

## Done

- SPEC-009 runtime implementation: strict decision/argument DTOs, domain call/write budgets,
  allowlisted adapters, fail-closed routing, checkpointed `create_task` proposal, sanitized runtime
  evidence, and idempotent API approval replay. Evidence: `tests/unit/application/use_cases/test_agent_tool_runtime.py`
  (9 passed), `tests/unit/infrastructure/agent` (10 passed), and `tests/integration/test_agent_runs_api.py`
  (4 passed); implementation commit `e0c4ac4`.
- SPEC-009 offline contract suite and adversarial coverage: `python -m evals.run --suite
  agent_tool_runtime_contract` scored 1.00 (8/8), `python -m evals.gate` passed all six suites, and
  `tests/adversarial/test_agent_tool_runtime_security.py` passed 3 cases alongside existing agent
  security tests. The full gate passed after the complete verification sequence.

- Item 3 exact retrieval adapter: active embedding-space resolution, tenant-scoped platform and
  organization selection, organization override before ranking, active revision and ready-state
  filtering, materialized eligible sources, exact pgvector cosine ranking, deterministic ordering,
  complete provenance, zero-vector integrity checks, and sanitized persistence errors. Commit
  `e02e529`; follow-up override evidence and four checked task lines in `096255c`.
- Application/domain hardening: float32-representable query validation, overflow-safe norm checks,
  zero-vector rejection, fixed public failure codes, and suppressed provider/SQL causes. Commit
  `e02e529`.
- Approved design and autonomous controls: exact retrieval decision in SPEC-008 docs and ADR-0016,
  item 3 scope expansion, UTF-8/local-checkout runtime environment, `ready_for_gate`, and
  `StopAfterItem`. Commit `737b285`; formal baseline rollover passed for six exact control paths.
- Focused evidence: 98 unit tests passed, the PostgreSQL retrieval integration passed with a
  synthetic platform/org override where the platform vector scored higher, and the item 3 gate
  reported Ruff, mypy, import-linter, unit/architecture tests, and agent docs all OK.
- Full verification: `pytest tests/unit tests/architecture -q` 440 passed; `pytest
  tests/integration -q` 46 passed; `pytest tests/adversarial -q` 13 passed; Ruff and format passed;
  mypy passed for 172 source files; import-linter kept 4 contracts; agent docs passed; all offline
  eval suites remained at 1.00; gitleaks reported no leaks.
- Item 4 internal composition wiring: `ApiSettings` and the API lifecycle now build the explicitly
  configured fake/OpenAI query embedding provider, while the request dependency composes
  `RetrieveKnowledge` with a request-scoped SQLAlchemy retrieval repository. The authenticated
  `/v1/knowledge/retrieve` route accepts only query, limit, and token budget, derives organization
  identity from JWT claims, and returns provenance plus omission reporting. No write or HITL route
  was changed. Evidence: `tests/unit/apps/test_knowledge_retrieval_wiring.py` (2 passed),
  `pytest tests/unit tests/architecture -q` (442 passed), and the knowledge API/retrieval
  PostgreSQL integration pair (2 passed).
- Post-commit verification: `pytest tests/integration -q` passed with 46 tests and 3 known
  SQLAlchemy pool-cleanup warnings; `lint-imports` kept 4 contracts, `check_agent_docs.py` passed,
  and `gitleaks detect --no-git` found no leaks.
- Merge verification: `git merge-tree --write-tree origin/develop HEAD` reported no conflicts;
  the full gate, PDF traceability check, and agent-docs check passed immediately before merge.
  Merge commit: `9ec47e3` on `develop`.
- Item 5 adversarial retrieval coverage: added injection-shaped and secret-shaped data fencing,
  rejection of caller-selected tenant/corpus/historical revision fields, trusted-tenant propagation,
  invalid limit/budget rejection, and sanitized persistence errors in
  `tests/adversarial/test_knowledge_retrieval_security.py`. Evidence: `pytest tests/adversarial -q`
  (23 passed), `pytest tests/unit tests/architecture -q` (442 passed), Ruff, mypy, and the Item 5
  gate all passed; the gate returned `GATE_EXIT=1` only because the task checkbox was not yet ticked.
- Post-commit Item 5 gate: Item 6 became the next queue item; Ruff, mypy, import-linter, unit/
  architecture tests, and agent docs were all `OK`, with `GATE_EXIT=1` only because Item 6 is not
  yet implemented or ticked. Commit `1a2b56f`; working tree is clean and no autonomous loop runs.
- Item 6 retrieval contract: added eight synthetic controlled-vector cases covering tenant
  filtering, active/ready membership, organization override before top-k, complete provenance,
  deterministic ordering, token-budget omissions, incompatible embedding spaces, and untrusted
  data fencing. Evidence: `python -m evals.run --suite rag_retrieval_contract` passed at 1.00
  (8/8); `python -m evals.gate` passed all five suites; 35 eval unit tests passed; Ruff, format,
  and mypy passed. Commit `9eca992`.
- Item 6 live smoke: `python scripts/check_rag_retrieval_live.py` refused without
  `--confirm-cost`; the explicitly confirmed invocation returned failure without making a live
  request because the provider configuration was absent. The smoke is optional and excluded from
  CI and the autonomous gate. Commit `9eca992`.
- Item 7 traceability: updated retrieval, source attribution, pgvector, and offline evaluation
  rows with concrete file/line evidence while retaining partial gaps for graph generation, reply
  classification, groundedness, and production metrics. Evidence: `python
  scripts/check_pdf_traceability.py` passed with 86 rows covering PDF pages 1-20. Commit `0991acc`.
- Item 8 closeout: Docker services became healthy with `docker compose up -d`; `pytest
  tests/integration -q` passed 46 tests against `postgresql+psycopg://revops:revops@localhost:5432/revops_item8b`
  with 3 known SQLAlchemy pool-cleanup warnings. Full verification passed: `ruff check .`, `ruff
  format --check .`, `mypy .`, `lint-imports`, `pytest tests/unit -q` (440 passed), `pytest
  tests/adversarial -q` (23 passed), `python -m evals.run --suite all` (5 suites passed), `python
  scripts/check_pdf_traceability.py`, `python scripts/check_agent_docs.py`, `gitleaks detect --no-git`,
  and `python scripts/autonomous_gate.py` (ruff, mypy, import-linter, pytest, and agent docs OK).
  Security review found no new secrets or adversarial regressions; Bandit retains four pre-existing
  low-severity B101 findings in ingestion assertions, `semgrep` is not installed, and `pip-audit`
  could not query PyPI because local TLS certificate verification failed. These tool limitations are
  recorded rather than treated as green results.

## Next

1. Publishing `develop` remains the user's action; this checkout's `origin` currently points to a
   local OneDrive repository rather than the GitHub URL.
2. Do not create an overnight loop until a future spec is materialized and its own queue is
   reviewed; SPEC-009 has no remaining implementation queue.

## Gotchas

- The working checkout is `C:\Dev\SISTEMA_PORTFOLIO_AI_ENG`; the original OneDrive checkout must
  not be used for this development loop.
- The supervisor baseline is `096255c` with done count 9; the ignored gate state is not committed.
- The database used for verification is the synthetic Docker database `revops_item8b`.
- Exact ranking is intentional. HNSW remains in the schema but is not the correctness mechanism for
  tenant filtering and organization override.
- API retrieval defaults to the deterministic offline provider; live OpenAI retrieval is explicit
  and requires `KNOWLEDGE_EMBEDDING_PROVIDER=openai` plus `OPENAI_API_KEY`.
- The old architecture-halt entries remain in git history; they do not represent the current
  implementation state.

## Resume

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'packages\core') + ';' + (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:DATABASE_URL = 'postgresql+psycopg://revops:revops@localhost:5432/revops_item8b'
python scripts/autonomous_gate.py
```

## Open questions

No product decision is currently open. Ambiguous requests remain a structured refusal without a
side effect; broader tools and clarification UX require later specs.
