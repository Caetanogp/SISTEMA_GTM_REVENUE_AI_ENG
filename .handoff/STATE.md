---
agent: codex
updated_at: 2026-09-12
branch: feature/SPEC-004-requirements-alignment
spec: SPEC-004-requirements-alignment
phase: "PDF requirements alignment and offline quality gate complete"
status: done; awaiting owner review and next spec decisions
---

# Current state

## Goal

Keep the repository faithful to `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf` by
making requirement coverage, implementation evidence and remaining gaps explicit before new product
development starts.

## Now

SPEC-004 has been reformulated from the superseded core-tools design into requirements alignment.
The branch contains a page-spanning PDF traceability matrix, a read-only source-hash/evidence
checker, CI enforcement for the supported offline eval suites, and corrected roadmap/documentation
references. No product runtime, database schema, API, UI, RAG or LLM provider code was changed.

The current branch is `feature/SPEC-004-requirements-alignment`. No push was performed. No
autonomous development loop is running. The old SPEC-003 autonomous queue and
`.handoff/.autonomous_gate_state.json` are historical controls and must not be used to start new
work without a new approved spec and queue.

## Done

- `0cc9106 docs(spec-004): align roadmap with project guide`: replaced the obsolete SPEC-004
  runtime design, added `docs/requirements/PDF_TRACEABILITY.md` with 86 rows covering PDF pages 1-20,
  corrected the roadmap/README and fixed stale SPEC-001 references.
- `a952025 fix(ci): enforce offline eval gate`: removed the provider-key skip and unsupported suite
  arguments from `.github/workflows/evals.yml`; CI now runs the traceability checker, supported
  offline suites and `python -m evals.gate`.
- `493aaad test(tooling): add PDF traceability checker`: added the standard-library checker and
  negative/positive tests in `tests/unit/scripts/test_pdf_traceability.py`.
- Source PDF hash verified as
  `8C294C58019722357B98BEF75B2E3CA7B52D3BE21891FF9D9F7C7D0B4D86E42A`.
- `python scripts/check_pdf_traceability.py` passed: `86 rows, pages 1-20 covered`.
- `pytest tests/unit/scripts/test_pdf_traceability.py -q` passed: `3 passed`.
- `pytest tests/unit -q` passed: `292 passed`.
- `ruff check .` passed; `ruff format --check .` passed: 172 files already formatted.
- `mypy .` passed: no issues in 135 source files.
- `lint-imports` passed: 4 contracts kept, 0 broken.
- `python scripts/check_agent_docs.py` and `git diff --check` passed.
- `python -m evals.run --suite all` passed: tool selection 13/13 and lead scoring 15/15.
- `python -m evals.gate` passed both thresholds.
- Pre-commit hooks passed on all three commits.
- A post-implementation evidence audit corrected five stale paths in the traceability matrix in
  `1b1fa8f fix(docs): correct traceability evidence paths`; the matrix and checker pass again.

## Not verified

- `docker compose ps` could not connect because Docker Desktop's Linux engine was unavailable.
  Therefore the existing SPEC-001 Docker/pgvector checklist item remains unchecked and no
  integration test result is claimed from this session.
- GitHub Actions has not run locally; the workflow was reviewed and its YAML pre-commit hook passed.

## Next

1. Owner reviews `docs/requirements/PDF_TRACEABILITY.md`, especially states marked `partial` or
   `planned`, and confirms that the PDF remains the source document at the recorded hash.
2. Owner decides the scope of the next real spec. The roadmap's natural candidate is
   `SPEC-005-crm-attribution-model`; numbers and scope remain deliberately changeable.
3. Materialize and approve that spec's `spec.md`, then its `plan.md` and `tasks.md`, before writing
   product code or creating a new autonomous queue.
4. The likely complex design decisions for later RAG, gateway and tool-runtime work require a
   deliberate design pass before implementation; do not infer those decisions from the roadmap.

## Gotchas

- RAG is intentionally planned for SPEC-007 and was not implemented or moved into this change.
- The superseded `SPEC-004-core-tools-reply-intelligence` documents were removed from the roadmap
  and replaced by `SPEC-004-requirements-alignment`; do not resume that old runtime scope.
- The matrix's `implemented` state is evidence-backed, while `partial` and `planned` are explicit
  gaps, not claims of completion.
- Never push from an agent. `develop` integrates verified feature branches; `main` remains hands-off.
- Do not launch an autonomous loop until a new approved spec, plan, tasks and queue exist.

## Resume

```powershell
git status --short
git rev-parse --abbrev-ref HEAD
python scripts/check_pdf_traceability.py
Get-Content docs/requirements/PDF_TRACEABILITY.md
Get-Content docs/specs/ROADMAP.md
```

## Open questions

- Owner review is required for the matrix's requirement interpretation and the next spec scope.
- Docker Desktop must be available before claiming the SPEC-001 pgvector/integration item.
