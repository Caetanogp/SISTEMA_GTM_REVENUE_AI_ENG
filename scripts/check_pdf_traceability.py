"""Validate the repository's traceability matrix against the source PDF."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "requirements" / "PDF_TRACEABILITY.md"
DEFAULT_PDF = ROOT / "docs" / "Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf"
REQUIRED_COLUMNS = (
    "ID",
    "PDF location",
    "Requirement",
    "Obligation",
    "State",
    "Owner spec",
    "Evidence or gap",
)
OBLIGATIONS = {"required", "recommended", "conditional", "not-required"}
STATES = {"implemented", "partial", "planned", "not-started", "not-applicable"}
ID_RE = re.compile(r"^PDF-\d{2}-\d{3}$")
HASH_RE = re.compile(r"PDF SHA-256:\s*`?([A-Fa-f0-9]{64})`?", re.IGNORECASE)
PAGE_RE = re.compile(r"PDF p\.\s*(\d+)", re.IGNORECASE)


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Return the required table header and data rows from Markdown text."""
    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if _cells(line) == list(REQUIRED_COLUMNS)),
        None,
    )
    if header_index is None:
        raise ValueError("traceability table with the required columns was not found")
    if header_index + 1 >= len(lines) or not _cells(lines[header_index + 1]):
        raise ValueError("traceability table is missing its separator row")

    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        row = _cells(line)
        if row:
            rows.append(row)
    if not rows:
        raise ValueError("traceability table has no data rows")
    return list(REQUIRED_COLUMNS), rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_matrix(matrix_path: Path = DEFAULT_MATRIX, pdf_path: Path = DEFAULT_PDF) -> list[str]:
    """Return all validation errors, without modifying either input file."""
    errors: list[str] = []
    if not matrix_path.is_file():
        return [f"matrix does not exist: {matrix_path}"]
    if not pdf_path.is_file():
        return [f"source PDF does not exist: {pdf_path}"]

    text = matrix_path.read_text(encoding="utf-8")
    expected_hash_match = HASH_RE.search(text)
    if expected_hash_match is None:
        errors.append("matrix is missing a 64-character PDF SHA-256")
    else:
        actual_hash = _sha256(pdf_path)
        if expected_hash_match.group(1).lower() != actual_hash:
            errors.append(
                "PDF SHA-256 mismatch: "
                f"matrix={expected_hash_match.group(1).lower()} actual={actual_hash}"
            )

    try:
        _, rows = parse_table(text)
    except ValueError as error:
        return [*errors, str(error)]

    ids: set[str] = set()
    pages: set[int] = set()
    for row_number, row in enumerate(rows, start=1):
        if len(row) != len(REQUIRED_COLUMNS):
            errors.append(
                f"row {row_number} has {len(row)} columns; expected {len(REQUIRED_COLUMNS)}"
            )
            continue
        identifier, location, requirement, obligation, state, owner, evidence = row
        if not ID_RE.fullmatch(identifier):
            errors.append(f"row {row_number} has invalid ID: {identifier!r}")
        elif identifier in ids:
            errors.append(f"duplicate ID: {identifier}")
        ids.add(identifier)
        page_match = PAGE_RE.search(location)
        if page_match is None:
            errors.append(f"row {row_number} has no PDF page location")
        else:
            pages.add(int(page_match.group(1)))
        for field_name, value in (
            ("location", location),
            ("requirement", requirement),
            ("obligation", obligation),
            ("state", state),
            ("owner", owner),
            ("evidence", evidence),
        ):
            if not value:
                errors.append(f"row {row_number} has an empty {field_name}")
        if obligation not in OBLIGATIONS:
            errors.append(f"row {row_number} has invalid obligation: {obligation!r}")
        if state not in STATES:
            errors.append(f"row {row_number} has invalid state: {state!r}")
        if state == "implemented" and (
            owner == "N/A"
            or evidence.strip().lower().startswith("n/a")
            or evidence.lower().startswith("gap:")
        ):
            errors.append(f"row {row_number} marks implemented without concrete evidence")
        if state not in {"implemented", "not-applicable"} and owner == "N/A":
            errors.append(f"row {row_number} needs an owner for state {state!r}")
        if state in {"partial", "planned", "not-started"} and "gap:" not in evidence.lower():
            errors.append(f"row {row_number} must state its gap")

    missing_pages = sorted(set(range(1, 21)) - pages)
    if missing_pages:
        errors.append(f"matrix has no row for PDF page(s): {', '.join(map(str, missing_pages))}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args(argv)
    errors = validate_matrix(args.matrix, args.pdf)
    if errors:
        print("PDF traceability check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    _, rows = parse_table(args.matrix.read_text(encoding="utf-8"))
    print(f"PDF traceability check passed: {len(rows)} rows, pages 1-20 covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
