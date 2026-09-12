# SPEC-004 tasks

Each item is independently verifiable. Do not mark an item complete without observed evidence.

## Traceability

- [x] Record the source PDF SHA-256 and complete page-spanning matrix in `docs/requirements/PDF_TRACEABILITY.md` - verified 2026-09-12 by `python scripts/check_pdf_traceability.py` (`86 rows, pages 1-20 covered`)
- [x] Add the read-only matrix checker in `scripts/check_pdf_traceability.py` - verified 2026-09-12 by its unit tests
- [x] Add malformed-input, hash-drift and evidence-honesty tests in `tests/unit/scripts/test_pdf_traceability.py` - verified 2026-09-12 by `pytest tests/unit/scripts/test_pdf_traceability.py -q` (`3 passed`)
- [x] Run the checker in CI - verified 2026-09-12 by `.github/workflows/evals.yml` inspection and workflow syntax review

## Eval gate

- [x] Make `.github/workflows/evals.yml` run supported offline suites without provider credentials - verified 2026-09-12 by workflow inspection and `python -m evals.run --suite all`
- [x] Enforce existing thresholds and upload the produced reports - verified 2026-09-12 by `python -m evals.gate` (`PASS` for both suites)

## Documentation alignment

- [x] Correct stale SPEC-001, README and roadmap status/scope references - verified 2026-09-12 by `rg "SPEC-002, phase 2|pending merge|SPEC-004-core-tools|feature/SPEC-001-agent-graph" README.md docs/specs/SPEC-001-vertical-slice-account-prioritization docs/specs/ROADMAP.md` returning no matches
- [x] Reconcile the SPEC-001 Docker/pgvector checkbox only with live command evidence - verified 2026-09-12 by `docker compose ps` failing because Docker Desktop is unavailable; the SPEC-001 checkbox remains unchecked

## Closeout

- [x] Run targeted tests, documentation checks, diff checks and supported offline evals - verified 2026-09-12 by checker, Ruff, mypy, import-linter, `pytest tests/unit -q` (`292 passed`), evals and `python scripts/check_agent_docs.py`
- [ ] Update `.handoff/STATE.md` with branch, commits, evidence and next owner decision - verified by file review
