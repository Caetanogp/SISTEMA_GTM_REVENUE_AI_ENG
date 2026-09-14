# SPEC-004 implementation plan

## Approach

Treat the project guide PDF as an immutable reviewed input and create a stable, page-spanning
traceability matrix. A small standard-library checker validates the matrix structure and source
hash. CI runs that checker together with the repository's existing deterministic offline eval gate.
Documentation is corrected to describe current implementation status without adding product code.

## Layers touched

- Documentation: `docs/requirements/`, `docs/specs/`, `docs/architecture` references and `README.md`.
- Quality tooling: `scripts/check_pdf_traceability.py` and its unit tests.
- CI: `.github/workflows/evals.yml` only.
- No domain, application, infrastructure, app, database or deployment runtime layer is touched.

## Contracts

The matrix contract is a Markdown table with these columns, in order:

`ID | PDF location | Requirement | Obligation | State | Owner spec | Evidence or gap`

IDs use `PDF-NN-NNN`, where `NN` is a stable requirement group and `NNN` is a stable row number;
the separate PDF location column is authoritative for page coverage. Obligation
is one of `required`, `recommended`, `conditional` or `not-required`. State is one of `implemented`,
`partial`, `planned`, `not-started` or `not-applicable`. Implemented rows require concrete evidence;
all other actionable rows require an owner and a stated gap.

## Design decisions

- **Standard library only:** the checker must run before optional development dependencies are
  installed and must not introduce a dependency or network call.
- **Hash the PDF:** page references alone cannot detect a revised source document. The SHA-256 is
  checked against the file in the same checkout.
- **Matrix, not generated claims:** evidence is reviewed text, so it remains readable in pull
  requests. The checker enforces honesty-shaped fields but does not infer implementation.
- **Offline evals always run:** provider credentials are not required for the current deterministic
  suites. Live evals can be added later as a separately named, optional job.
- **Minimum PDF scope:** compatible extensions already present in the repository remain documented,
  but they do not turn planned PDF capabilities into implemented ones.

## Test and verification plan

- Unit-test valid parsing, duplicate IDs, malformed rows, invalid states, missing ownership/evidence,
  source hash mismatch and page coverage.
- Run the checker against the real PDF and matrix.
- Run `python -m evals.run --suite all` and `python -m evals.gate` using the existing offline data.
- Run `python scripts/check_agent_docs.py`, `git diff --check`, targeted unit tests and the relevant
  lint/type/import checks.

## Rollout

Merge this documentation/tooling feature only after the checker and offline eval gate pass on the
feature branch. Do not push, publish a PR or launch an autonomous queue from this change. The next
spec must be written and approved from the revised roadmap before implementation resumes.
