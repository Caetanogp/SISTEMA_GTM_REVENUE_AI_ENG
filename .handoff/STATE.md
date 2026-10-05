---
agent: codex
updated_at: 2026-10-04
branch: feature/SPEC-008-context-retrieval
spec: SPEC-008-context-retrieval
phase: "Item 5 adversarial retrieval coverage implemented and verified"
status: pilot_complete_item_5
---

# Current state

## Goal

Implement PDF-aligned task-scoped knowledge retrieval in SPEC-008.

## Now

SPEC-008 items 1-5 are complete: 11 of 15 task checkboxes are checked. Item 6 is the next queue
item. No autonomous loop is running. The bounded Item 5 validation was completed in the main
checkout because the earlier supervisor architecture review halted before implementation.

## Done

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
- Item 5 adversarial retrieval coverage: added injection-shaped and secret-shaped data fencing,
  rejection of caller-selected tenant/corpus/historical revision fields, trusted-tenant propagation,
  invalid limit/budget rejection, and sanitized persistence errors in
  `tests/adversarial/test_knowledge_retrieval_security.py`. Evidence: `pytest tests/adversarial -q`
  (23 passed), `pytest tests/unit tests/architecture -q` (442 passed), Ruff, mypy, and the Item 5
  gate all passed; the gate returned `GATE_EXIT=1` only because the task checkbox was not yet ticked.
- Post-commit Item 5 gate: Item 6 became the next queue item; Ruff, mypy, import-linter, unit/
  architecture tests, and agent docs were all `OK`, with `GATE_EXIT=1` only because Item 6 is not
  yet implemented or ticked. Commit `1a2b56f`; working tree is clean and no autonomous loop runs.

## Next

1. Implement Item 6 deterministic retrieval eval and explicitly cost-confirmed live-smoke guard.
2. Run the Item 6 bounded pilot and gate before marking its two task checkboxes.
3. Continue through the remaining SPEC-008 items; do not launch an overnight loop until the queue
   contract and gate prove the next item is architecture-stable.

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

None for Item 5. Item 6 is the next implementation item; no product-scope or architecture choice
is currently awaiting the user.
